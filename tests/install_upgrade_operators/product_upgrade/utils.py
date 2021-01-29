import logging
import re
from multiprocessing import Process

from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.cluster_version import ClusterVersion
from ocp_resources.datavolume import DataVolume
from ocp_resources.deployment import Deployment
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.installplan import InstallPlan
from ocp_resources.package_manifest import PackageManifest
from ocp_resources.pod import Pod
from ocp_resources.resource import Resource, ResourceEditor
from ocp_resources.subscription import Subscription
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from ocp_resources.virtual_machine import VirtualMachineInstanceMigration
from openshift.dynamic.exceptions import (
    InternalServerError,
    NotFoundError,
    ResourceNotFoundError,
)

from utilities.constants import TIMEOUT_10MIN, TIMEOUT_60MIN
from utilities.hco import wait_for_hco_conditions
from utilities.virt import run_command, wait_for_vm_interfaces


APP_REGISTRY = "rh-osbs-operators"
LOGGER = logging.getLogger(__name__)


def wait_for_dvs_import_completed(dvs_list):
    def _dvs_import_completed():
        return all(map(lambda dv: dv.status == DataVolume.Status.SUCCEEDED, dvs_list))

    LOGGER.info("Wait for DVs import to end.")
    samples = TimeoutSampler(
        wait_timeout=1200,
        sleep=10,
        func=_dvs_import_completed,
    )
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
def wait_for_operator_replacement(
    dyn_client, hco_namespace, operator_name, old_operator_pod
):

    operator_sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=1,
        func=get_operator_by_name,
        dyn_client=dyn_client,
        hco_namespace=hco_namespace,
        operator_name=operator_name,
    )

    for operator in operator_sampler:
        LOGGER.debug(
            f"Old operator: {old_operator_pod.name} new operator: {operator.name}"
        )
        if operator.name != old_operator_pod.name:
            return operator


def pod_status_and_image(
    dyn_client,
    hco_namespace,
    operators_version,
    old_operators_pods,
    delete_pod=False,
):
    """
    Wait for a new operator pod to be created.
    If delete_pod - new operator pods will be deleted (test operator
    resiliency)
    """

    oper_name, image_ver = operators_version
    LOGGER.info(f"Verify operator pod {oper_name} replacement.")

    old_operators_pod = [pod for pod in old_operators_pods if oper_name in pod.name]

    if old_operators_pod:
        new_operator_pod = wait_for_operator_replacement(
            dyn_client=dyn_client,
            hco_namespace=hco_namespace,
            operator_name=oper_name,
            old_operator_pod=old_operators_pod[0],
        )
    # For new operators which did not exist in a previous version
    else:
        new_operator_pod = get_operator_by_name(
            dyn_client=dyn_client,
            hco_namespace=hco_namespace,
            operator_name=oper_name,
        )

    LOGGER.info(
        f"Wait for {new_operator_pod.name} to get updated image version {image_ver}"
    )
    image_sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=1,
        func=lambda: new_operator_pod.instance.spec.containers[0].image == image_ver,
    )

    for image_sample in image_sampler:
        if image_sample:
            if delete_pod:
                new_operator_pod.delete(wait=True, force=True)
                # Operator pod is deleted, fetching a new pod
                new_operator_pod = get_operator_by_name(
                    dyn_client=dyn_client,
                    hco_namespace=hco_namespace,
                    operator_name=oper_name,
                )
            new_operator_pod.wait_for_condition(
                condition=Pod.Condition.READY,
                status=Pod.Condition.Status.TRUE,
                timeout=TIMEOUT_10MIN,
            )

            break


def check_pods_status_and_images(
    dyn_client, hco_namespace, old_operators_pods, operators_versions, delete_pods
):
    LOGGER.info(
        "Check that all operators PODs have been replaced and have new images version and have status ready."
        f"Pods will {'' if delete_pods else 'not'} be deleted."
    )

    processes = []

    for operators_version in operators_versions.items():
        p = Process(
            target=pod_status_and_image,
            kwargs={
                "dyn_client": dyn_client,
                "hco_namespace": hco_namespace,
                "operators_version": operators_version,
                "old_operators_pods": old_operators_pods,
                "delete_pod": delete_pods,
            },
        )
        processes.append(p)
        p.start()

    for process in processes:
        process.join()

    assert set([process.exitcode for process in processes]) == {0}


def get_operators_names_and_images(csv):
    operators_versions = {}
    for deploy in csv.instance.spec.install.spec.deployments:
        operators_versions[deploy.name] = deploy.spec.template.spec.containers[0].image
    return operators_versions


def get_new_csv(dyn_client, hco_namespace, hco_target_version):
    for csv in ClusterServiceVersion.get(
        dyn_client=dyn_client, namespace=hco_namespace
    ):
        if csv.name == hco_target_version:
            return csv


def get_clusterversion(dyn_client):
    for cvo in ClusterVersion.get(dyn_client=dyn_client):
        return cvo


def wait_for_csv(dyn_client, hco_namespace, hco_target_version):
    csv_sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=1,
        func=get_new_csv,
        dyn_client=dyn_client,
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


def update_subscription_channel(dyn_client, hco_namespace, target_version):
    LOGGER.info("Change subscription channel.")
    for subscription in Subscription.get(
        dyn_client=dyn_client, namespace=hco_namespace
    ):
        if subscription.name == "hco-operatorhub":
            ResourceEditor(
                {
                    subscription: {
                        "spec": {"channel": target_version, "source": APP_REGISTRY}
                    }
                }
            ).update()


def get_install_plan(dyn_client, hco_namespace, hco_target_version):
    for ip in InstallPlan.get(dyn_client=dyn_client, namespace=hco_namespace):
        if hco_target_version == ip.instance.spec.clusterServiceVersionNames[0]:
            return ip

    return


def approve_install_plan(install_plan):
    ip_dict = install_plan.instance.to_dict()
    ip_dict["spec"]["approved"] = True
    install_plan.update(resource_dict=ip_dict)
    install_plan.wait_for_status(
        status=install_plan.Status.COMPLETE, timeout=TIMEOUT_10MIN
    )


def wait_for_install_plan(dyn_client, hco_namespace, hco_target_version):
    samples = TimeoutSampler(
        wait_timeout=120,
        sleep=1,
        func=get_install_plan,
        dyn_client=dyn_client,
        hco_namespace=hco_namespace,
        hco_target_version=hco_target_version,
    )
    for sample in samples:
        if sample:
            return sample


def get_cluster_pods(dyn_client, hco_namespace, pods_type):
    """
    Returns a list of cluster pods:
    pods_type - operator/tier-2 (non-operator) /all
    """
    pods = list(Pod.get(dyn_client=dyn_client, namespace=hco_namespace))
    cluster_pods = []
    for pod in pods:
        # Operator pods
        if pods_type == "operator" and "operator" in pod.name:
            cluster_pods.append(pod)
        # Tier-2 pods (created by operators)
        elif pods_type == "tier-2" and "operator" not in pod.name:
            cluster_pods.append(pod)
        # All pods
        else:
            cluster_pods.append(pod)

    assert cluster_pods
    return cluster_pods


def get_operator_by_name(dyn_client, hco_namespace, operator_name):
    pods = list(Pod.get(dyn_client=dyn_client, namespace=hco_namespace))
    operator_pod = list(filter(lambda x: operator_name in x.name, pods))[0]
    return operator_pod


def get_images_from_manifest(dyn_client, hco_namespace, target_version):
    for package in PackageManifest.get(dyn_client=dyn_client, namespace=hco_namespace):
        if package.name == "kubevirt-hyperconverged":
            return [
                channel.currentCSVDesc.relatedImages
                for channel in package.instance.status.channels
                if channel.currentCSV == target_version
            ][0]


def check_tier2_pods_images(dyn_client, hco_namespace, hco_target_version):
    updated_images_list = get_images_from_manifest(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace,
        target_version=hco_target_version,
    )
    cluster_pods = get_cluster_pods(
        dyn_client=dyn_client, hco_namespace=hco_namespace, pods_type="tier-2"
    )

    unreplaced_pods = [
        pod.name
        for pod in cluster_pods
        if pod.instance.spec.containers[0].image not in updated_images_list
    ]

    assert (
        not unreplaced_pods
    ), f"The following pods images were not replaced: {unreplaced_pods}"


def get_hyperconverged_cr(dyn_client, namespace):
    for cr in HyperConverged.get(dyn_client=dyn_client, namespace=namespace):
        return cr


def get_nodes_status(nodes):
    nodes_dict = {}
    for node in nodes:
        node_conditions = [
            {condition.type: condition.status}
            for condition in node.instance.status.conditions
        ]
        nodes_dict[node.name] = {
            "labels": node.instance.metadata.labels,
            "taints": node.instance.spec.taints,
            "unschedulable": node.instance.unschedulable,
            "conditions": node_conditions,
        }

    return nodes_dict


def verify_nodes_status_after_upgrade(nodes, nodes_status_before_upgrade):
    nodes_status_after_upgrade = None
    nodes_sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=5,
        func=get_nodes_status,
        nodes=nodes,
    )

    try:
        for nodes_status_after_upgrade in nodes_sampler:
            if nodes_status_after_upgrade == nodes_status_before_upgrade:
                return

    except TimeoutExpiredError:
        LOGGER.error(
            f"Nodes before upgrade: {nodes_status_before_upgrade}, nodes after upgrade: {nodes_status_after_upgrade}"
        )
        raise


def verify_cnv_pods_are_running(dyn_client, hco_namespace):
    cnv_pods = get_cluster_pods(
        dyn_client=dyn_client, hco_namespace=hco_namespace.name, pods_type="all"
    )
    failed_pods = [pod.name for pod in cnv_pods if pod.status != Pod.Status.RUNNING]
    assert not failed_pods, f"Some CNV pods are not running: {failed_pods}"


def upgrade_cnv(dyn_client, hco_namespace, cnv_upgrade_path, upgrade_resilience):
    LOGGER.info(f"CNV upgrade: {cnv_upgrade_path}")
    hco_target_version = (
        f"kubevirt-hyperconverged-operator.v{cnv_upgrade_path['target_version']}"
    )
    LOGGER.info("Get all operators PODs before upgrade")
    old_operators_pods = get_cluster_pods(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace.name,
        pods_type="operator",
    )
    all_old_pods = get_cluster_pods(
        dyn_client=dyn_client, hco_namespace=hco_namespace.name, pods_type="all"
    )

    LOGGER.info("Update subscription channel and source.")
    update_subscription_channel(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace.name,
        target_version=cnv_upgrade_path["target_channel"],
    )

    LOGGER.info("Approve the install plan to trigger the upgrade.")
    approve_install_plan(
        install_plan=wait_for_install_plan(
            dyn_client=dyn_client,
            hco_namespace=hco_namespace.name,
            hco_target_version=hco_target_version,
        )
    )

    LOGGER.info("Wait for a new CSV")
    new_csv = wait_for_csv(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace.name,
        hco_target_version=hco_target_version,
    )

    LOGGER.info("Check that CSV status is Installing")
    new_csv.wait_for_status(
        status=new_csv.Status.INSTALLING, timeout=TIMEOUT_10MIN, stop_status=None
    )

    LOGGER.info("Get all operators PODs names and images version from the new CSV")
    operators_versions = get_operators_names_and_images(csv=new_csv)

    LOGGER.info("Wait for operators replacement.")
    check_pods_status_and_images(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace.name,
        old_operators_pods=old_operators_pods,
        operators_versions=operators_versions,
        delete_pods=upgrade_resilience,
    )

    LOGGER.info("Wait for HCO conditions after upgrade")
    wait_for_hco_conditions(admin_client=dyn_client)

    LOGGER.info("Wait for HCO operator to be ready")
    hco_operator_pod = get_operator_by_name(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace.name,
        operator_name="hco-operator",
    )
    hco_operator_pod.wait_for_condition(
        condition=Pod.Condition.READY,
        status=Pod.Condition.Status.TRUE,
        timeout=TIMEOUT_10MIN,
    )

    LOGGER.info("Wait for number of replicas = number of updated replicas")
    for deploy in Deployment.get(dyn_client, namespace=hco_namespace.name):
        deploy.wait_for_replicas(timeout=TIMEOUT_10MIN)

    LOGGER.info("Wait for the new HCO to be available.")
    for hco in HyperConverged.get(dyn_client=dyn_client, namespace=hco_namespace.name):
        hco.wait_for_condition(
            condition=Pod.Condition.AVAILABLE, status=Pod.Condition.Status.TRUE
        )

    LOGGER.info("Check that CSV status is Succeeded")
    new_csv.wait_for_status(
        status=new_csv.Status.SUCCEEDED, timeout=TIMEOUT_10MIN, stop_status=None
    )

    LOGGER.info("Verify all previous pods were deleted")
    undeleted_pods = [pod.name for pod in all_old_pods if pod.exists]
    assert not undeleted_pods, f"Some old pods were not deleted: {undeleted_pods}"

    LOGGER.info("Verify tier-2 pods images were updated")
    check_tier2_pods_images(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace.name,
        hco_target_version=hco_target_version,
    )


def extract_ocp_version(ocp_image):
    # Extract the OCP version from the OCP URL input.
    ocp_version = re.search(r":(\d+\.\d+\.\d+)-(rc\.\d+)?", ocp_image)
    assert (
        ocp_version
    ), f"Cannot extract OCP version. OCP image url: {ocp_image} is invalid"
    return "-".join(filter(None, ocp_version.groups()))


def wait_until_ocp_upgrade_complete(ocp_image, dyn_client):
    LOGGER.info("Wait for upgrade to complete")

    upgrade_conditions = {
        "Available": Resource.Condition.Status.TRUE,
        "Failing": Resource.Condition.Status.FALSE,
        "Progressing": Resource.Condition.Status.TRUE,
    }
    actual_conditions = None
    ocp_version = extract_ocp_version(ocp_image=ocp_image)

    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_60MIN,
        sleep=10,
        func=get_clusterversion,
        exceptions=(
            NotFoundError,
            ResourceNotFoundError,
            InternalServerError,
        ),
        dyn_client=dyn_client,
    )

    try:
        for sample in samples:
            if sample:
                actual_conditions = sample.instance.status.conditions
                actual_upgrade_conditions = {
                    condition.type: condition.status
                    for condition in actual_conditions
                    if condition.type in upgrade_conditions.keys()
                }

                if (
                    actual_upgrade_conditions == upgrade_conditions
                    and sample.instance.status.history[0].version == ocp_version
                    and sample.instance.status.history[0].state == "Completed"
                ):
                    return

    except TimeoutExpiredError:
        LOGGER.error(
            f"Expected conditions: {upgrade_conditions}. Actual conditions: {actual_conditions}"
        )
        raise


def upgrade_ocp(ocp_image, dyn_client):
    assert run_command(
        command=[
            "oc",
            "adm",
            "upgrade",
            "--force=true",
            "--allow-explicit-upgrade",
            "--to-image",
            ocp_image,
        ]
    )[1], "OCP upgrade command failed."

    wait_until_ocp_upgrade_complete(ocp_image=ocp_image, dyn_client=dyn_client)
