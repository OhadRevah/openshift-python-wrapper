import logging
from ipaddress import ip_interface

import pytest
from pytest_testconfig import config as py_config
from resources.datavolume import DataVolume
from resources.deployment import Deployment
from resources.hyperconverged import HyperConverged
from tests.network.utils import assert_ping_successful
from tests.product_upgrade.utils import TIMEOUT_10MIN, UpgradeUtils
from utilities import console
from utilities.virt import (
    check_ssh_connection,
    enable_ssh_service_in_vm,
    vm_console_run_commands,
)


LOGGER = logging.getLogger(__name__)


@pytest.mark.upgrade
@pytest.mark.incremental
@pytest.mark.usefixtures("skip_when_one_node")
class TestUpgrade:
    @pytest.mark.run(before="test_upgrade")
    @pytest.mark.polarion("CNV-2974")
    def test_is_vm_running_before_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            assert vm.vmi.status == "Running"

    @pytest.mark.run(after="test_is_vm_running_before_upgrade")
    @pytest.mark.polarion("CNV-2975")
    def test_migration_before_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            if vm.template_dv.access_modes == DataVolume.AccessMode.RWO:
                LOGGER.info(f"Cannot migrate a VM {vm.name} with RWO PVC.")
                continue
            UpgradeUtils.migrate_vm_and_validate(vm=vm, when="before")

    @pytest.mark.run(after="test_migration_before_upgrade")
    @pytest.mark.polarion("CNV-2988")
    def test_vm_have_2_interfaces_before_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            assert len(vm.vmi.interfaces) == 2

    @pytest.mark.run(after="test_migration_before_upgrade")
    @pytest.mark.polarion("CNV-2987")
    def test_vm_console_before_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            vm_console_run_commands(console_impl=console.RHEL, vm=vm, commands=["ls"])

    @pytest.mark.polarion("CNV-4208")
    @pytest.mark.run(after="test_migration_before_upgrade")
    def test_vm_ssh_before_upgrade(self, schedulable_node_ips, vms_for_upgrade):
        for vm in vms_for_upgrade:
            enable_ssh_service_in_vm(vm=vm, console_impl=console.RHEL)
            assert check_ssh_connection(
                ip=list(schedulable_node_ips.values())[0],
                port=vm.ssh_node_port,
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
        UpgradeUtils.assert_bridge_and_vms_on_same_node(
            vm_a=running_vm_a, vm_b=running_vm_b, bridge=bridge_on_one_node
        )
        UpgradeUtils.assert_node_is_marked_by_bridge(
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
        old_pods = UpgradeUtils.get_all_operators_pods(default_client, hco_namespace)
        old_pods_names = [pod.name for pod in old_pods]

        LOGGER.info("Approve the install plan to trigger the upgrade.")
        UpgradeUtils.approve_install_plan(
            default_client, hco_namespace, new_hco_version
        )

        LOGGER.info("Wait for the new CSV")
        new_csv = UpgradeUtils.wait_for_csv(
            default_client, hco_namespace, new_hco_version, UpgradeUtils.get_new_csv
        )

        LOGGER.info("Check that CSV status is Installing")
        new_csv.wait_for_status(
            new_csv.Status.INSTALLING, timeout=TIMEOUT_10MIN, stop_status=None
        )

        LOGGER.info("Get all operators PODs names and images version from the new CSV")
        operators_versions = UpgradeUtils.get_operators_names_and_images(new_csv)

        LOGGER.info("Wait for old operators PODs to disappear")
        UpgradeUtils.wait_pods_deleted(old_pods_names, old_pods)

        LOGGER.info("Get all operators PODs after upgrade")
        new_pods = UpgradeUtils.get_all_operators_pods(default_client, hco_namespace)

        LOGGER.info(
            "Check that all operators PODs have the new images version and have status ready"
        )
        UpgradeUtils.check_pods_status_and_images(new_pods, operators_versions)

        LOGGER.info("Wait for HCO operator to be ready")
        hco_operator_pod = UpgradeUtils.get_hco_operator(default_client, hco_namespace)
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
    def test_is_vm_running_after_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            vm.vmi.wait_until_running()

    @pytest.mark.run(after="test_is_vm_running_after_upgrade")
    @pytest.mark.polarion("CNV-2989")
    def test_vm_have_2_interfaces_after_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            assert len(vm.vmi.interfaces) == 2

    @pytest.mark.run(after="test_is_vm_running_after_upgrade")
    @pytest.mark.polarion("CNV-2980")
    def test_vm_console_after_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            vm_console_run_commands(console_impl=console.RHEL, vm=vm, commands=["ls"])

    @pytest.mark.polarion("CNV-4209")
    @pytest.mark.run(after="test_is_vm_running_after_upgrade")
    def test_vm_ssh_after_upgrade(self, schedulable_node_ips, vms_for_upgrade):
        for vm in vms_for_upgrade:
            assert check_ssh_connection(
                ip=list(schedulable_node_ips.values())[0],
                port=vm.ssh_node_port,
                console_impl=console.RHEL,
            ), "Failed to login via SSH"

    @pytest.mark.run(after="test_vm_console_after_upgrade")
    @pytest.mark.polarion("CNV-2979")
    def test_migration_after_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            if vm.template_dv.access_modes == DataVolume.AccessMode.RWO:
                LOGGER.info(f"Cannot migrate a VM {vm.name} with RWO PVC.")
                continue
            UpgradeUtils.migrate_vm_and_validate(vm=vm, when="after")
            assert len(vm.vmi.interfaces) == 2
            vm_console_run_commands(
                console_impl=console.RHEL, vm=vm, commands=["ls"], timeout=1100
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
        UpgradeUtils.assert_bridge_and_vms_on_same_node(
            vm_a=running_vm_a, vm_b=running_vm_b, bridge=bridge_on_one_node
        )
        UpgradeUtils.assert_node_is_marked_by_bridge(
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
