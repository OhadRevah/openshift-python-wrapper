import logging
from ipaddress import ip_interface

import pytest
from pytest_testconfig import config as py_config
from resources.clusterserviceversion import ClusterServiceVersion
from resources.deployment import Deployment
from resources.hyperconverged import HyperConverged
from resources.installplan import InstallPlan
from resources.pod import Pod
from resources.utils import TimeoutSampler
from resources.virtual_machine import VirtualMachineInstanceMigration
from tests.network.utils import assert_ping_successful
from utilities import console
from utilities.virt import (
    check_ssh_connection,
    enable_ssh_service_in_vm,
    vm_console_run_commands,
)


LOGGER = logging.getLogger(__name__)
TIMEOUT_10MIN = 10 * 60


@pytest.mark.upgrade
@pytest.mark.incremental
@pytest.mark.usefixtures("skip_when_one_node", "dv_for_upgrade")
class TestUpgrade:
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

    @pytest.mark.run(before="test_upgrade")
    @pytest.mark.polarion("CNV-2974")
    def test_is_vm_running_before_upgrade(self, vm_for_upgrade):
        assert vm_for_upgrade.vmi.status == "Running"

    @pytest.mark.run(after="test_is_vm_running_before_upgrade")
    @pytest.mark.polarion("CNV-2975")
    def test_migration_before_upgrade(self, vm_for_upgrade):
        self.migrate_vm_and_validate(vm=vm_for_upgrade, when="before")

    @pytest.mark.run(after="test_migration_before_upgrade")
    @pytest.mark.polarion("CNV-2988")
    def test_vm_have_2_interfaces_before_upgrade(self, vm_for_upgrade):
        assert len(vm_for_upgrade.vmi.interfaces) == 2

    @pytest.mark.run(after="test_migration_before_upgrade")
    @pytest.mark.polarion("CNV-2987")
    def test_vm_console_before_upgrade(self, vm_for_upgrade):
        vm_console_run_commands(
            console_impl=console.RHEL, vm=vm_for_upgrade, commands=["ls"]
        )

    @pytest.mark.polarion("CNV-4208")
    @pytest.mark.run(after="test_migration_before_upgrade")
    def test_vm_ssh_before_upgrade(self, schedulable_node_ips, vm_for_upgrade):
        enable_ssh_service_in_vm(vm=vm_for_upgrade, console_impl=console.RHEL)
        assert check_ssh_connection(
            ip=list(schedulable_node_ips.values())[0],
            port=vm_for_upgrade.ssh_node_port,
            console_impl=console.RHEL,
        ), "Failed to login via SSH"

    @pytest.mark.run(before="test_upgrade")
    @pytest.mark.polarion("CNV-2743")
    def test_nmstate_bridge_before_upgrade(self, bridge_on_one_node):
        bridge_on_one_node.validate_create()

    @pytest.mark.run(after="test_nmstate_bridge_before_upgrade")
    @pytest.mark.polarion("CNV-2744")
    def test_bridge_marker_before_upgrade(
        self,
        vm_upgrade_a,
        vm_upgrade_b,
        running_vm_a,
        running_vm_b,
        upgrade_bridge_marker_nad,
        bridge_on_one_node,
    ):
        self.assert_bridge_and_vms_on_same_node(
            vm_a=running_vm_a, vm_b=running_vm_b, bridge=bridge_on_one_node
        )
        self.assert_node_is_marked_by_bridge(
            bridge_nad=upgrade_bridge_marker_nad, vm=running_vm_b
        )

    @pytest.mark.run(after="test_nmstate_bridge_before_upgrade")
    @pytest.mark.polarion("CNV-2745")
    def test_linux_bridge_before_upgrade(
        self, vm_upgrade_a, vm_upgrade_b, running_vm_a, running_vm_b
    ):
        dst_ip_address = ip_interface(
            running_vm_b.vmi.instance.status.interfaces[1].ipAddress
        ).ip
        assert_ping_successful(src_vm=running_vm_a, dst_ip=str(dst_ip_address))

    @pytest.mark.polarion("CNV-2991")
    def test_upgrade(self, default_client):
        new_hco_version = "kubevirt-hyperconverged-operator.v2.1.0"
        hco_namespace = py_config["hco_namespace"]

        LOGGER.info("Get all operators PODs before upgrade")
        old_pods = self.get_all_operators_pods(default_client, hco_namespace)
        old_pods_names = [pod.name for pod in old_pods]

        LOGGER.info("Approve the install plan to trigger the upgrade.")
        self.approve_install_plan(default_client, hco_namespace, new_hco_version)

        LOGGER.info("Wait for the new CSV")
        new_csv = self.wait_for_csv(
            default_client, hco_namespace, new_hco_version, self.get_new_csv
        )

        LOGGER.info("Check that CSV status is Installing")
        new_csv.wait_for_status(
            new_csv.Status.INSTALLING, timeout=TIMEOUT_10MIN, stop_status=None
        )

        LOGGER.info("Get all operators PODs names and images version from the new CSV")
        operators_versions = self.get_operators_names_and_images(new_csv)

        LOGGER.info("Wait for old operators PODs to disappear")
        self.wait_pods_deleted(old_pods_names, old_pods)

        LOGGER.info("Get all operators PODs after upgrade")
        new_pods = self.get_all_operators_pods(default_client, hco_namespace)

        LOGGER.info(
            "Check that all operators PODs have the new images version and have status ready"
        )
        self.check_pods_status_and_images(new_pods, operators_versions)

        LOGGER.info("Wait for HCO operator to be ready")
        hco_operator_pod = self.get_hco_operator(default_client, hco_namespace)
        hco_operator_pod.wait_for_condition(condition="Ready", status="True")

        LOGGER.info("Wait for number of replicas = number of updated replicas")
        for deploy in Deployment.get(default_client, namespace=hco_namespace):
            deploy.wait_until_avail_replicas(timeout=TIMEOUT_10MIN)

        LOGGER.info("Wait for the new HCO to be available.")
        for hco in HyperConverged.get(
            dyn_client=default_client, namespace=hco_namespace
        ):
            hco.wait_for_condition(condition="Available", status="True")

        LOGGER.info("Check that CSV status is Succeeded")
        new_csv.wait_for_status(
            new_csv.Status.SUCCEEDED, timeout=TIMEOUT_10MIN, stop_status=None
        )

    @pytest.mark.run(after="test_upgrade")
    @pytest.mark.polarion("CNV-2978")
    def test_is_vm_running_after_upgrade(self, vm_for_upgrade):
        vm_for_upgrade.vmi.wait_until_running()

    @pytest.mark.run(after="test_is_vm_running_after_upgrade")
    @pytest.mark.polarion("CNV-2989")
    def test_vm_have_2_interfaces_after_upgrade(self, vm_for_upgrade):
        assert len(vm_for_upgrade.vmi.interfaces) == 2

    @pytest.mark.run(after="test_is_vm_running_after_upgrade")
    @pytest.mark.polarion("CNV-2980")
    def test_vm_console_after_upgrade(self, vm_for_upgrade):
        vm_console_run_commands(
            console_impl=console.RHEL, vm=vm_for_upgrade, commands=["ls"]
        )

    @pytest.mark.polarion("CNV-4209")
    @pytest.mark.run(after="test_is_vm_running_after_upgrade")
    def test_vm_ssh_after_upgrade(self, schedulable_node_ips, vm_for_upgrade):
        assert check_ssh_connection(
            ip=list(schedulable_node_ips.values())[0],
            port=vm_for_upgrade.ssh_node_port,
            console_impl=console.RHEL,
        ), "Failed to login via SSH"

    @pytest.mark.run(after="test_vm_console_after_upgrade")
    @pytest.mark.polarion("CNV-2979")
    def test_migration_after_upgrade(self, vm_for_upgrade):
        self.migrate_vm_and_validate(vm=vm_for_upgrade, when="after")
        assert len(vm_for_upgrade.vmi.interfaces) == 2
        vm_console_run_commands(
            console_impl=console.RHEL, vm=vm_for_upgrade, commands=["ls"], timeout=1100
        )

    @pytest.mark.run(after="test_upgrade")
    @pytest.mark.polarion("CNV-2747")
    def test_nmstate_bridge_after_upgrade(self, bridge_on_one_node):
        bridge_on_one_node.validate_create()

    @pytest.mark.run(after="test_nmstate_bridge_after_upgrade")
    @pytest.mark.polarion("CNV-2749")
    def test_bridge_marker_after_upgrade(
        self,
        vm_upgrade_a,
        vm_upgrade_b,
        running_vm_a,
        running_vm_b,
        upgrade_bridge_marker_nad,
        bridge_on_one_node,
    ):
        self.assert_bridge_and_vms_on_same_node(
            vm_a=running_vm_a, vm_b=running_vm_b, bridge=bridge_on_one_node
        )
        self.assert_node_is_marked_by_bridge(
            bridge_nad=upgrade_bridge_marker_nad, vm=running_vm_b
        )

    @pytest.mark.run(after="test_nmstate_bridge_after_upgrade")
    @pytest.mark.polarion("CNV-2748")
    def test_linux_bridge_after_upgrade(
        self, vm_upgrade_a, vm_upgrade_b, running_vm_a, running_vm_b
    ):
        dst_ip_address = ip_interface(
            running_vm_b.vmi.instance.status.interfaces[1].ipAddress
        ).ip
        assert_ping_successful(src_vm=running_vm_a, dst_ip=str(dst_ip_address))
