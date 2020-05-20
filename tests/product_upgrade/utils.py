import logging
import re

from pytest_testconfig import py_config
from resources.cluster_service_version import ClusterServiceVersion
from resources.datavolume import DataVolume
from resources.deployment import Deployment
from resources.hyperconverged import HyperConverged
from resources.installplan import InstallPlan
from resources.pod import Pod
from resources.resource import ResourceEditor
from resources.subscription import Subscription
from resources.utils import TimeoutSampler
from resources.virtual_machine import VirtualMachineInstanceMigration
from utilities.virt import wait_for_vm_interfaces


APP_REGISTRY = "redhat-operators-stage"
LOGGER = logging.getLogger(__name__)
TIMEOUT_10MIN = 10 * 60


def wait_for_dvs_import_completed(dvs_list):
    def _dvs_import_completed():
        return all(map(lambda dv: dv.status == DataVolume.Status.SUCCEEDED, dvs_list))

    LOGGER.info("Wait for DVs import to end.")
    samples = TimeoutSampler(timeout=900, sleep=10, func=_dvs_import_completed,)
    for sample in samples:
        if sample:
            return


def wait_for_vms_interfaces(vms_list):
    for vm in vms_list:
        wait_for_vm_interfaces(vmi=vm.vmi, timeout=1100)


def migrate_vm_and_validate(vm, when):
    vmi_node_before_migration = vm.vmi.instance.status.nodeName
    with VirtualMachineInstanceMigration(
        name=f"{when}-upgrade-migration", namespace=vm.namespace, vmi=vm.vmi
    ) as mig:
        mig.wait_for_status(status=mig.Status.SUCCEEDED, timeout=720)
        assert vm.vmi.instance.status.nodeName != vmi_node_before_migration
        assert vm.vmi.instance.status.migrationState.completed


def assert_bridge_and_vms_on_same_node(vm_a, vm_b, bridge):
    for vm in [vm_a, vm_b]:
        assert vm.vmi.node.name == bridge.node_selector


def assert_node_is_marked_by_bridge(bridge_nad, vm):
    for bridge_annotation in bridge_nad.instance.metadata.annotations.values():
        assert bridge_annotation in vm.vmi.node.instance.status.capacity.keys()
        assert bridge_annotation in vm.vmi.node.instance.status.allocatable.keys()


# Upgrade-related functions


def check_pods_status_and_images(pods, operators_versions):
    for pod in pods:
        for oper_name, image_ver in operators_versions.items():
            if oper_name in pod.name:
                image_sampler = TimeoutSampler(
                    timeout=TIMEOUT_10MIN,
                    sleep=1,
                    func=lambda: pod.instance.spec.containers[0].image == image_ver,
                )
                LOGGER.info(
                    f"Wait for {pod.name} to get updated image version {image_ver}"
                )
                for image_sample in image_sampler:
                    if image_sample:
                        pod.wait_for_condition(
                            condition="Ready", status="True", timeout=TIMEOUT_10MIN
                        )
                        break
                break


def wait_pods_deleted(old_pods_names, pods):
    for pod in pods:
        if pod.name in old_pods_names:
            pod.wait_deleted(timeout=TIMEOUT_10MIN)


def get_operators_names_and_images(csv):
    operators_versions = {}
    for deploy in csv.instance.spec.install.spec.deployments:
        operators_versions[deploy.name] = deploy.spec.template.spec.containers[0].image
    return operators_versions


def get_current_cnv_version(dyn_client, hco_namespace):
    for csv in ClusterServiceVersion.get(
        dyn_client=dyn_client, namespace=hco_namespace
    ):
        return csv.instance.spec.version


def get_new_csv(default_client, hco_namespace, hco_target_version):
    for csv in ClusterServiceVersion.get(
        dyn_client=default_client, namespace=hco_namespace
    ):
        if csv.name == hco_target_version:
            return csv


def wait_for_csv(default_client, hco_namespace, hco_target_version):
    csv_sampler = TimeoutSampler(
        timeout=TIMEOUT_10MIN,
        sleep=1,
        func=get_new_csv,
        default_client=default_client,
        hco_namespace=hco_namespace,
        hco_target_version=hco_target_version,
    )
    for csv_sample in csv_sampler:
        if csv_sample:
            return csv_sample


def upgrade_path(cnv_upgrade_dict):
    current_version = re.search(
        r"([0-9]+)\.([0-9]+)\.([0-9]+)", cnv_upgrade_dict["current_version"]
    )
    target_version = re.search(
        r"([0-9]+)\.([0-9]+)\.([0-9]+)", cnv_upgrade_dict["target_version"]
    )
    target_channel = ".".join(target_version.group(1, 2))

    if current_version.group(1) < target_version.group(1):
        return "x-stream", target_channel
    elif current_version.group(2) < target_version.group(2):
        return "y-stream", target_channel
    elif current_version.group(3) < target_version.group(3):
        return "z-stream", target_channel


def update_subscription_channel(default_client, hco_namespace, target_version):
    LOGGER.info("Change subscription channel.")
    for subscription in Subscription.get(
        dyn_client=default_client, namespace=hco_namespace
    ):
        if subscription.name == "hco-operatorhub":
            ResourceEditor(
                {
                    subscription: {
                        "spec": {"channel": target_version, "source": APP_REGISTRY}
                    }
                }
            ).update()


def get_install_plan(default_client, hco_namespace, hco_target_version):
    for ip in InstallPlan.get(dyn_client=default_client, namespace=hco_namespace):
        if hco_target_version == ip.instance.spec.clusterServiceVersionNames[0]:
            return ip

    return


def approve_install_plan(install_plan):
    ip_dict = install_plan.instance.to_dict()
    ip_dict["spec"]["approved"] = True
    install_plan.update(ip_dict)
    install_plan.wait_for_status(install_plan.Status.COMPLETE, timeout=TIMEOUT_10MIN)


def wait_for_install_plan(default_client, hco_namespace, hco_target_version):
    samples = TimeoutSampler(
        timeout=120,
        sleep=1,
        func=get_install_plan,
        default_client=default_client,
        hco_namespace=hco_namespace,
        hco_target_version=hco_target_version,
    )
    for sample in samples:
        if sample:
            return sample


def get_all_operators_pods(default_client, hco_namespace):
    pods = list(Pod.get(dyn_client=default_client, namespace=hco_namespace))
    pods = [_pod for _pod in pods if "operator" in _pod.name]
    assert pods
    return pods


def get_hco_operator(default_client, hco_namespace):
    pods = list(Pod.get(dyn_client=default_client, namespace=hco_namespace))
    hco_operator_pod = list(filter(lambda x: "hco-operator" in x.name, pods))[0]
    return hco_operator_pod


def upgrade_cnv(default_client, cnv_upgrade_path):
    LOGGER.info(f"CNV upgrade: {cnv_upgrade_path}")
    hco_target_version = (
        f"kubevirt-hyperconverged-operator.v{cnv_upgrade_path['target_version']}"
    )
    hco_namespace = py_config["hco_namespace"]
    LOGGER.info("Get all operators PODs before upgrade")
    old_pods = get_all_operators_pods(default_client, hco_namespace)
    old_pods_names = [pod.name for pod in old_pods]

    if cnv_upgrade_path["upgrade_path"] == "x-stream":
        LOGGER.info("Update subscription channel for x-stream upgrade.")
        update_subscription_channel(
            default_client=default_client,
            hco_namespace=hco_namespace,
            target_version=cnv_upgrade_path["target_channel"],
        )

    if cnv_upgrade_path["upgrade_path"] == "y-stream":
        LOGGER.info("Update subscription channel for y-stream upgrade.")
        update_subscription_channel(
            default_client=default_client,
            hco_namespace=hco_namespace,
            target_version=cnv_upgrade_path["target_channel"],
        )

    LOGGER.info("Approve the install plan to trigger the upgrade.")
    approve_install_plan(
        install_plan=wait_for_install_plan(
            default_client=default_client,
            hco_namespace=hco_namespace,
            hco_target_version=hco_target_version,
        )
    )

    LOGGER.info("Wait for the new CSV")
    new_csv = wait_for_csv(
        default_client=default_client,
        hco_namespace=hco_namespace,
        hco_target_version=hco_target_version,
    )

    LOGGER.info("Check that CSV status is Installing")
    new_csv.wait_for_status(
        new_csv.Status.INSTALLING, timeout=TIMEOUT_10MIN, stop_status=None
    )

    LOGGER.info("Get all operators PODs names and images version from the new CSV")
    operators_versions = get_operators_names_and_images(new_csv)

    LOGGER.info("Wait for old operators PODs to disappear")
    wait_pods_deleted(old_pods_names=old_pods_names, pods=old_pods)

    LOGGER.info("Get all operators PODs after upgrade")
    new_pods = get_all_operators_pods(
        default_client=default_client, hco_namespace=hco_namespace
    )

    LOGGER.info(
        "Check that all operators PODs have the new images version and have status ready"
    )
    check_pods_status_and_images(pods=new_pods, operators_versions=operators_versions)

    LOGGER.info("Wait for HCO operator to be ready")
    hco_operator_pod = get_hco_operator(
        default_client=default_client, hco_namespace=hco_namespace
    )
    hco_operator_pod.wait_for_condition(condition="Ready", status="True")

    LOGGER.info("Wait for number of replicas = number of updated replicas")
    for deploy in Deployment.get(default_client, namespace=hco_namespace):
        deploy.wait_until_avail_replicas(timeout=TIMEOUT_10MIN)

    LOGGER.info("Wait for the new HCO to be available.")
    for hco in HyperConverged.get(dyn_client=default_client, namespace=hco_namespace):
        hco.wait_for_condition(condition="Available", status="True")

    LOGGER.info("Check that CSV status is Succeeded")
    new_csv.wait_for_status(
        new_csv.Status.SUCCEEDED, timeout=TIMEOUT_10MIN, stop_status=None
    )
