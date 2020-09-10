import logging
from ipaddress import ip_interface

import pytest
import tests.product_upgrade.utils as upgrade_utils
from resources.datavolume import DataVolume
from tests.network.utils import assert_ping_successful
from utilities import console
from utilities.network import get_vmi_mac_address_by_iface_name
from utilities.virt import (
    check_ssh_connection,
    enable_ssh_service_in_vm,
    vm_console_run_commands,
)


LOGGER = logging.getLogger(__name__)


@pytest.mark.upgrade
@pytest.mark.incremental
@pytest.mark.usefixtures(
    "skip_when_one_node", "cnv_upgrade_path", "nodes_status_before_upgrade"
)
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
            upgrade_utils.migrate_vm_and_validate(vm=vm, when="before")

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
        running_vm_upgrade_a,
        running_vm_upgrade_b,
        upgrade_bridge_marker_nad,
        bridge_on_one_node,
    ):
        upgrade_utils.assert_bridge_and_vms_on_same_node(
            vm_a=running_vm_upgrade_a,
            vm_b=running_vm_upgrade_b,
            bridge=bridge_on_one_node,
        )
        upgrade_utils.assert_node_is_marked_by_bridge(
            bridge_nad=upgrade_bridge_marker_nad, vm=running_vm_upgrade_b
        )

    @pytest.mark.polarion("CNV-2745")
    @pytest.mark.run(after="test_nmstate_bridge_before_upgrade")
    def test_linux_bridge_before_upgrade(
        self, vm_upgrade_a, vm_upgrade_b, running_vm_upgrade_a, running_vm_upgrade_b
    ):
        dst_ip_address = ip_interface(
            address=running_vm_upgrade_b.vmi.instance.status.interfaces[1].ipAddress
        ).ip
        assert_ping_successful(src_vm=running_vm_upgrade_a, dst_ip=str(dst_ip_address))

    @pytest.mark.polarion("CNV-2745")
    @pytest.mark.run(after="test_nmstate_bridge_before_upgrade")
    def test_kubemacpool_before_upgrade(
        self,
        vm_upgrade_a,
        vm_upgrade_b,
        running_vm_upgrade_a,
        running_vm_upgrade_b,
        mac_pool,
        upgrade_bridge_marker_nad,
    ):
        for vm in (running_vm_upgrade_a, running_vm_upgrade_b):
            assert mac_pool.mac_is_within_range(
                mac=get_vmi_mac_address_by_iface_name(
                    vmi=vm.vmi, iface_name=upgrade_bridge_marker_nad.name
                )
            )

    @pytest.mark.upgrade_resilience
    @pytest.mark.polarion("CNV-2991")
    @pytest.mark.run(after="test_linux_bridge_before_upgrade")
    def test_upgrade(
        self,
        pytestconfig,
        admin_client,
        hco_namespace,
        cnv_upgrade_path,
        operatorhub_no_default_sources,
        operator_source,
    ):
        if pytestconfig.option.upgrade == "ocp":
            upgrade_utils.upgrade_ocp(
                ocp_image=pytestconfig.option.ocp_image, dyn_client=admin_client
            )

        if pytestconfig.option.upgrade == "cnv":
            upgrade_utils.upgrade_cnv(
                dyn_client=admin_client,
                hco_namespace=hco_namespace,
                cnv_upgrade_path=cnv_upgrade_path,
                upgrade_resilience=pytestconfig.option.upgrade_resilience,
            )

    @pytest.mark.polarion("CNV-4509")
    @pytest.mark.run(after="test_upgrade")
    def test_cnv_pods_running_after_upgrade(self, admin_client, hco_namespace):
        LOGGER.info("Verify CNV pods running after upgrade.")
        upgrade_utils.verify_cnv_pods_are_running(
            dyn_client=admin_client, hco_namespace=hco_namespace
        )

    @pytest.mark.polarion("CNV-4510")
    @pytest.mark.run(after="test_upgrade")
    def test_nodes_status_after_upgrade(self, nodes, nodes_status_before_upgrade):
        LOGGER.info("Verify nodes status after upgrade.")
        upgrade_utils.verify_nodes_status_after_upgrade(
            nodes=nodes, nodes_status_before_upgrade=nodes_status_before_upgrade
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
            upgrade_utils.migrate_vm_and_validate(vm=vm, when="after")
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
        running_vm_upgrade_a,
        running_vm_upgrade_b,
        upgrade_bridge_marker_nad,
        bridge_on_one_node,
    ):
        upgrade_utils.assert_bridge_and_vms_on_same_node(
            vm_a=running_vm_upgrade_a,
            vm_b=running_vm_upgrade_b,
            bridge=bridge_on_one_node,
        )
        upgrade_utils.assert_node_is_marked_by_bridge(
            bridge_nad=upgrade_bridge_marker_nad, vm=running_vm_upgrade_b
        )

    @pytest.mark.polarion("CNV-2748")
    @pytest.mark.run(after="test_nmstate_bridge_after_upgrade")
    def test_linux_bridge_after_upgrade(
        self, vm_upgrade_a, vm_upgrade_b, running_vm_upgrade_a, running_vm_upgrade_b
    ):
        dst_ip_address = ip_interface(
            address=running_vm_upgrade_b.vmi.instance.status.interfaces[1].ipAddress
        ).ip
        assert_ping_successful(src_vm=running_vm_upgrade_a, dst_ip=str(dst_ip_address))

    @pytest.mark.polarion("CNV-2746")
    @pytest.mark.run(after="test_nmstate_bridge_after_upgrade")
    def test_kubemacpool_after_upgrade(
        self,
        vm_upgrade_a,
        vm_upgrade_b,
        running_vm_upgrade_a,
        running_vm_upgrade_b,
        mac_pool,
        upgrade_bridge_marker_nad,
    ):
        for vm in (running_vm_upgrade_a, running_vm_upgrade_b):
            assert mac_pool.mac_is_within_range(
                mac=get_vmi_mac_address_by_iface_name(
                    vmi=vm.vmi, iface_name=upgrade_bridge_marker_nad.name
                )
            )

    @pytest.mark.polarion("CNV-3682")
    @pytest.mark.run(after="test_upgrade")
    def test_machine_type_after_upgrade(
        self, vms_for_upgrade, vms_for_upgrade_dict_before
    ):
        for vm in vms_for_upgrade:
            assert (
                vm.instance.spec.template.spec.domain.machine.type
                == vms_for_upgrade_dict_before[vm.name]["spec"]["template"]["spec"][
                    "domain"
                ]["machine"]["type"]
            )
