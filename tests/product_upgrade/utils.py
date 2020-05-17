import logging

from resources.clusterserviceversion import ClusterServiceVersion
from resources.datavolume import DataVolume
from resources.installplan import InstallPlan
from resources.pod import Pod
from resources.utils import TimeoutSampler
from resources.virtual_machine import VirtualMachineInstanceMigration
from utilities.virt import wait_for_vm_interfaces


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


class UpgradeUtils:
    @staticmethod
    def check_pods_status_and_images(pods, operators_versions):
        for pod in pods:
            for oper_name, image_ver in operators_versions.items():
                if oper_name in pod.name:
                    image_sampler = TimeoutSampler(
                        timeout=TIMEOUT_10MIN,
                        sleep=1,
                        func=lambda: pod.instance.spec.containers[0].image == image_ver,
                    )
                    LOGGER.info(f"Wait for {pod.name} to get updated image version")
                    for image_sample in image_sampler:
                        if image_sample:
                            pod.wait_for_condition(
                                condition="Ready", status="True", timeout=TIMEOUT_10MIN
                            )
                            break
                    break

    @staticmethod
    def wait_pods_deleted(old_pods_names, pods):
        for pod in pods:
            if pod.name in old_pods_names:
                pod.wait_deleted(timeout=TIMEOUT_10MIN)

    @staticmethod
    def get_operators_names_and_images(csv):
        operators_versions = {}
        for deploy in csv.instance.spec.install.spec.deployments:
            operators_versions[deploy.name] = deploy.spec.template.spec.containers[
                0
            ].image
        return operators_versions

    @staticmethod
    def migrate_vm_and_validate(vm, when):
        vmi_node_before_migration = vm.vmi.instance.status.nodeName
        with VirtualMachineInstanceMigration(
            name=f"{when}-upgrade-migration", namespace=vm.namespace, vmi=vm.vmi
        ) as mig:
            mig.wait_for_status(status=mig.Status.SUCCEEDED, timeout=720)
            assert vm.vmi.instance.status.nodeName != vmi_node_before_migration
            assert vm.vmi.instance.status.migrationState.completed

    @staticmethod
    def get_new_csv(default_client, hco_namespace, new_hco_version):
        for csv in ClusterServiceVersion.get(
            dyn_client=default_client, namespace=hco_namespace
        ):
            if csv.name == new_hco_version:
                return csv

    @staticmethod
    def wait_for_csv(default_client, hco_namespace, new_hco_version, get_new_csv):
        csv_sampler = TimeoutSampler(
            timeout=TIMEOUT_10MIN,
            sleep=1,
            func=get_new_csv,
            default_client=default_client,
            hco_namespace=hco_namespace,
            new_hco_version=new_hco_version,
        )
        for csv_sample in csv_sampler:
            if csv_sample:
                csv = csv_sample
                return csv

    @staticmethod
    def approve_install_plan(default_client, hco_namespace, new_hco_version):
        for ip in InstallPlan.get(dyn_client=default_client, namespace=hco_namespace):
            if new_hco_version == ip.instance.spec.clusterServiceVersionNames[0]:
                ip_dict = ip.instance.to_dict()
                ip_dict["spec"]["approved"] = True
                ip.update(ip_dict)
                ip.wait_for_status(ip.Status.COMPLETE, timeout=TIMEOUT_10MIN)

    @staticmethod
    def get_all_operators_pods(default_client, hco_namespace):
        pods = list(Pod.get(dyn_client=default_client, namespace=hco_namespace))
        pods = [_pod for _pod in pods if "operator" in _pod.name]
        assert pods
        return pods

    @staticmethod
    def get_hco_operator(default_client, hco_namespace):
        pods = list(Pod.get(dyn_client=default_client, namespace=hco_namespace))
        hco_operator_pod = list(filter(lambda x: "hco-operator" in x.name, pods))[0]
        return hco_operator_pod

    @staticmethod
    def assert_bridge_and_vms_on_same_node(vm_a, vm_b, bridge):
        for vm in [vm_a, vm_b]:
            assert vm.vmi.node.name == bridge.node_selector

    @staticmethod
    def assert_node_is_marked_by_bridge(bridge_nad, vm):
        for bridge_annotation in bridge_nad.instance.metadata.annotations.values():
            assert bridge_annotation in vm.vmi.node.instance.status.capacity.keys()
            assert bridge_annotation in vm.vmi.node.instance.status.allocatable.keys()
