import logging
from ipaddress import ip_interface

import pytest
from resources.datavolume import DataVolume
from tests.network.utils import assert_ping_successful
from tests.product_upgrade.utils import UpgradeUtils
from utilities import console
from utilities.virt import (
    check_ssh_connection,
    enable_ssh_service_in_vm,
    vm_console_run_commands,
)


LOGGER = logging.getLogger(__name__)


@pytest.mark.upgrade
@pytest.mark.incremental
@pytest.mark.usefixtures("skip_when_one_node", "cnv_versions")
class TestUpgrade:
    @pytest.mark.polarion("CNV-2974")
    @pytest.mark.run(before="test_upgrade")
    def test_is_vm_running_before_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            assert vm.vmi.status == "Running"

    @pytest.mark.polarion("CNV-2975")
    @pytest.mark.run(after="test_is_vm_running_before_upgrade")
    def test_migration_before_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            if vm.template_dv.access_modes == DataVolume.AccessMode.RWO:
                LOGGER.info(f"Cannot migrate a VM {vm.name} with RWO PVC.")
                continue
            UpgradeUtils.migrate_vm_and_validate(vm=vm, when="before")

    @pytest.mark.polarion("CNV-2988")
    @pytest.mark.run(after="test_migration_before_upgrade")
    def test_vm_have_2_interfaces_before_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            assert len(vm.vmi.interfaces) == 2

    @pytest.mark.polarion("CNV-2987")
    @pytest.mark.run(after="test_migration_before_upgrade")
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

    @pytest.mark.polarion("CNV-2743")
    @pytest.mark.run(before="test_upgrade")
    def test_nmstate_bridge_before_upgrade(self, bridge_on_one_node):
        bridge_on_one_node.validate_create()

    @pytest.mark.polarion("CNV-2744")
    @pytest.mark.run(after="test_nmstate_bridge_before_upgrade")
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

    @pytest.mark.polarion("CNV-2745")
    @pytest.mark.run(after="test_nmstate_bridge_before_upgrade")
    def test_linux_bridge_before_upgrade(
        self, vm_upgrade_a, vm_upgrade_b, running_vm_a, running_vm_b
    ):
        dst_ip_address = ip_interface(
            running_vm_b.vmi.instance.status.interfaces[1].ipAddress
        ).ip
        assert_ping_successful(src_vm=running_vm_a, dst_ip=str(dst_ip_address))

    @pytest.mark.polarion("CNV-2991")
    @pytest.mark.run(after="test_linux_bridge_before_upgrade")
    def test_upgrade(self, pytestconfig, default_client, cnv_versions):
        # TODO: OCP upgrade tests are in progress

        if pytestconfig.option.upgrade == "cnv":
            UpgradeUtils.upgrade_cnv(
                default_client=default_client,
                cnv_target_version=cnv_versions["target_version"],
            )

    @pytest.mark.polarion("CNV-2978")
    @pytest.mark.run(after="test_upgrade")
    def test_is_vm_running_after_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            vm.vmi.wait_until_running()

    @pytest.mark.polarion("CNV-2989")
    @pytest.mark.run(after="test_is_vm_running_after_upgrade")
    def test_vm_have_2_interfaces_after_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            assert len(vm.vmi.interfaces) == 2

    @pytest.mark.polarion("CNV-2980")
    @pytest.mark.run(after="test_is_vm_running_after_upgrade")
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

    @pytest.mark.polarion("CNV-2979")
    @pytest.mark.run(after="test_vm_console_after_upgrade")
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

    @pytest.mark.polarion("CNV-2747")
    @pytest.mark.run(after="test_upgrade")
    def test_nmstate_bridge_after_upgrade(self, bridge_on_one_node):
        bridge_on_one_node.validate_create()

    @pytest.mark.polarion("CNV-2749")
    @pytest.mark.run(after="test_nmstate_bridge_after_upgrade")
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

    @pytest.mark.polarion("CNV-2748")
    @pytest.mark.run(after="test_nmstate_bridge_after_upgrade")
    def test_linux_bridge_after_upgrade(
        self, vm_upgrade_a, vm_upgrade_b, running_vm_a, running_vm_b
    ):
        dst_ip_address = ip_interface(
            running_vm_b.vmi.instance.status.interfaces[1].ipAddress
        ).ip
        assert_ping_successful(src_vm=running_vm_a, dst_ip=str(dst_ip_address))
