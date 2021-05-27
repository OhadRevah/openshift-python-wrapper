import logging
from ipaddress import ip_interface

import pytest
from ocp_resources.datavolume import DataVolume

import tests.install_upgrade_operators.product_upgrade.utils as upgrade_utils
from utilities import console
from utilities.constants import KMP_ENABLED_LABEL, KMP_VM_ASSIGNMENT_LABEL
from utilities.network import (
    assert_ping_successful,
    get_vmi_mac_address_by_iface_name,
    verify_ovs_installed_with_annotations,
)
from utilities.virt import migrate_vm_and_verify, vm_console_run_commands


LOGGER = logging.getLogger(__name__)


@pytest.mark.upgrade
@pytest.mark.usefixtures(
    "skip_when_one_node", "cnv_upgrade_path", "nodes_status_before_upgrade"
)
class TestUpgrade:
    @pytest.mark.polarion("CNV-2974")
    @pytest.mark.order(before="test_upgrade_process")
    @pytest.mark.dependency(name="test_is_vm_running_before_upgrade")
    def test_is_vm_running_before_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            assert vm.vmi.status == "Running"

    @pytest.mark.polarion("CNV-2975")
    @pytest.mark.order(before="test_upgrade_process")
    @pytest.mark.dependency(
        name="test_migration_before_upgrade",
        depends=["test_is_vm_running_before_upgrade"],
    )
    def test_migration_before_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            if vm.data_volume.access_modes == DataVolume.AccessMode.RWO:
                LOGGER.info(f"Cannot migrate a VM {vm.name} with RWO PVC.")
                continue
            migrate_vm_and_verify(
                vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False
            )

    @pytest.mark.polarion("CNV-2988")
    @pytest.mark.order(before="test_upgrade_process")
    @pytest.mark.dependency(
        name="test_vm_have_2_interfaces_before_upgrade",
        depends=["test_is_vm_running_before_upgrade"],
    )
    def test_vm_have_2_interfaces_before_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            assert len(vm.vmi.interfaces) == 2

    @pytest.mark.polarion("CNV-2987")
    @pytest.mark.order(before="test_upgrade_process")
    @pytest.mark.dependency(
        name="test_vm_console_before_upgrade",
        depends=["test_is_vm_running_before_upgrade"],
    )
    def test_vm_console_before_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            vm_console_run_commands(console_impl=console.RHEL, vm=vm, commands=["ls"])

    @pytest.mark.polarion("CNV-4208")
    @pytest.mark.order(before="test_upgrade_process")
    @pytest.mark.dependency(
        name="test_vm_ssh_before_upgrade",
        depends=["test_is_vm_running_before_upgrade"],
    )
    def test_vm_ssh_before_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            assert vm.ssh_exec.executor().is_connective(
                tcp_timeout=120
            ), "Failed to login via SSH"

    @pytest.mark.polarion("CNV-2743")
    @pytest.mark.order(before="test_upgrade_process")
    @pytest.mark.dependency(name="test_nmstate_bridge_before_upgrade")
    def test_nmstate_bridge_before_upgrade(self, bridge_on_one_node):
        bridge_on_one_node.validate_create()

    @pytest.mark.polarion("CNV-2744")
    @pytest.mark.order(before="test_upgrade_process")
    @pytest.mark.dependency(name="test_bridge_marker_before_upgrade")
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
    @pytest.mark.order(before="test_upgrade_process")
    @pytest.mark.dependency(name="test_linux_bridge_before_upgrade")
    def test_linux_bridge_before_upgrade(
        self,
        vm_upgrade_a,
        vm_upgrade_b,
        running_vm_upgrade_a,
        running_vm_upgrade_b,
        upgrade_bridge_marker_nad,
        bridge_on_one_node,
    ):
        dst_ip_address = ip_interface(
            address=running_vm_upgrade_b.vmi.instance.status.interfaces[1].ipAddress
        ).ip
        assert_ping_successful(src_vm=running_vm_upgrade_a, dst_ip=str(dst_ip_address))

    @pytest.mark.polarion("CNV-5944")
    @pytest.mark.order(before="test_upgrade_process")
    @pytest.mark.dependency(name="test_kubemacpool_enabled_ns_before_upgrade")
    def test_kubemacpool_enabled_ns_before_upgrade(
        self,
        kmp_vm_label,
    ):
        # KubeMacPool is enabled in namespace.
        assert kmp_vm_label.get(KMP_VM_ASSIGNMENT_LABEL) == KMP_ENABLED_LABEL

    @pytest.mark.polarion("CNV-2745")
    @pytest.mark.order(before="test_upgrade_process")
    @pytest.mark.dependency(name="test_kubemacpool_before_upgrade")
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

    @pytest.mark.polarion("CNV-4880")
    @pytest.mark.order(before="test_upgrade_process")
    @pytest.mark.dependency(name="test_cdiconfig_scratch_overriden_before_upgrade")
    def test_cdiconfig_scratch_overriden_before_upgrade(
        self,
        cdi_config,
        storage_class_for_updating_cdiconfig_scratch,
        override_cdiconfig_scratch_spec,
    ):
        """
        Check that the scratch StorageClass configuration should be changed before CNV upgrade
        """
        expected_sc = (
            storage_class_for_updating_cdiconfig_scratch.instance.metadata.name
        )
        actual_sc = cdi_config.scratch_space_storage_class_from_status
        assert (
            actual_sc == expected_sc
        ), "The scratchSpaceStorageClass on CDIConfig config should be changed before upgrade"

    @pytest.mark.polarion("CNV-5659")
    @pytest.mark.order(before="test_upgrade_process")
    @pytest.mark.dependency(name="test_install_ovs_with_annotations_before_upgrade")
    def test_install_ovs_with_annotations_before_upgrade(
        self,
        admin_client,
        hco_namespace,
        hyperconverged_resource_scope_function,
        network_addons_config,
        hyperconverged_ovs_annotations_enabled_scope_class,
        hyperconverged_ovs_annotations_fetched,
    ):
        # Verify ovs annotation has been enabled (opt-in)
        assert (
            hyperconverged_ovs_annotations_fetched
        ), "OVS hasn't been opt-in as needed."

    @pytest.mark.upgrade_resilience
    @pytest.mark.polarion("CNV-2991")
    @pytest.mark.dependency(name="test_upgrade_process")
    def test_upgrade_process(
        self,
        pytestconfig,
        admin_client,
        hco_namespace,
        hco_target_version,
        hco_current_version,
        cnv_upgrade_path,
        operatorhub_without_default_sources,
        cnv_registry_source,
        update_image_content_source,
        cnv_source,
    ):
        if pytestconfig.option.upgrade == "ocp":
            upgrade_utils.upgrade_ocp(
                ocp_image=pytestconfig.option.ocp_image,
                dyn_client=admin_client,
                ocp_channel=pytestconfig.option.ocp_channel,
            )

        if pytestconfig.option.upgrade == "cnv":
            upgrade_utils.upgrade_cnv(
                dyn_client=admin_client,
                hco_namespace=hco_namespace,
                hco_target_version=hco_target_version,
                hco_current_version=hco_current_version,
                image=pytestconfig.option.cnv_image,
                cnv_upgrade_path=cnv_upgrade_path,
                upgrade_resilience=pytestconfig.option.upgrade_resilience,
                cnv_subscription_source=cnv_registry_source["cnv_subscription_source"],
                cnv_source=cnv_source,
            )

    @pytest.mark.polarion("CNV-4509")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(depends=["test_upgrade_process"])
    def test_cnv_pods_running_after_upgrade(self, admin_client, hco_namespace):
        LOGGER.info("Verify CNV pods running after upgrade.")
        upgrade_utils.verify_cnv_pods_are_running(
            dyn_client=admin_client, hco_namespace=hco_namespace
        )

    @pytest.mark.polarion("CNV-4510")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(depends=["test_upgrade_process"])
    def test_nodes_status_after_upgrade(self, nodes, nodes_status_before_upgrade):
        LOGGER.info("Verify nodes status after upgrade.")
        upgrade_utils.verify_nodes_status_after_upgrade(
            nodes=nodes, nodes_status_before_upgrade=nodes_status_before_upgrade
        )

    @pytest.mark.polarion("CNV-2978")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(
        depends=["test_upgrade_process", "test_is_vm_running_before_upgrade"]
    )
    def test_is_vm_running_after_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            vm.vmi.wait_until_running()

    @pytest.mark.polarion("CNV-2989")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(
        depends=["test_upgrade_process", "test_vm_have_2_interfaces_before_upgrade"]
    )
    def test_vm_have_2_interfaces_after_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            assert len(vm.vmi.interfaces) == 2

    @pytest.mark.polarion("CNV-2980")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(
        depends=["test_upgrade_process", "test_vm_console_before_upgrade"]
    )
    def test_vm_console_after_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            vm_console_run_commands(console_impl=console.RHEL, vm=vm, commands=["ls"])

    @pytest.mark.polarion("CNV-4209")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(
        depends=["test_upgrade_process", "test_vm_ssh_before_upgrade"]
    )
    def test_vm_ssh_after_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            assert vm.ssh_exec.executor().is_connective(
                tcp_timeout=120
            ), "Failed to login via SSH"

    @pytest.mark.polarion("CNV-2979")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(
        depends=["test_upgrade_process", "test_migration_before_upgrade"]
    )
    def test_migration_after_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            if vm.data_volume.access_modes == DataVolume.AccessMode.RWO:
                LOGGER.info(f"Cannot migrate a VM {vm.name} with RWO PVC.")
                continue
            migrate_vm_and_verify(vm=vm)
            assert len(vm.vmi.interfaces) == 2
            vm_console_run_commands(
                console_impl=console.RHEL, vm=vm, commands=["ls"], timeout=1100
            )

    @pytest.mark.polarion("CNV-2747")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(
        depends=["test_upgrade_process", "test_nmstate_bridge_before_upgrade"]
    )
    def test_nmstate_bridge_after_upgrade(self, bridge_on_one_node):
        bridge_on_one_node.validate_create()

    @pytest.mark.polarion("CNV-2749")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(
        depends=["test_upgrade_process", "test_bridge_marker_before_upgrade"]
    )
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
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(
        depends=["test_upgrade_process", "test_linux_bridge_before_upgrade"]
    )
    def test_linux_bridge_after_upgrade(
        self,
        vm_upgrade_a,
        vm_upgrade_b,
        running_vm_upgrade_a,
        running_vm_upgrade_b,
        upgrade_bridge_marker_nad,
        bridge_on_one_node,
    ):
        dst_ip_address = ip_interface(
            address=running_vm_upgrade_b.vmi.instance.status.interfaces[1].ipAddress
        ).ip
        assert_ping_successful(src_vm=running_vm_upgrade_a, dst_ip=str(dst_ip_address))

    @pytest.mark.polarion("CNV-2746")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(
        depends=["test_upgrade_process", "test_kubemacpool_before_upgrade"]
    )
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

    @pytest.mark.polarion("CNV-5945")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(
        depends=["test_upgrade_process", "test_kubemacpool_enabled_ns_before_upgrade"]
    )
    def test_kubemacpool_enabled_ns_after_upgrade(
        self,
        kmp_vm_label,
    ):
        # KubeMacPool is still enabled in namespace.
        assert kmp_vm_label.get(KMP_VM_ASSIGNMENT_LABEL) == KMP_ENABLED_LABEL

    @pytest.mark.polarion("CNV-3682")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(depends=["test_upgrade_process"])
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

    @pytest.mark.polarion("CNV-4725")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(depends=["test_upgrade_process"])
    def test_dv_api_version_after_upgrade(self, dvs_for_upgrade):
        for dv in dvs_for_upgrade:
            assert dv.api_version == f"{dv.api_group}/{dv.ApiVersion.V1BETA1}"

    @pytest.mark.polarion("CNV-2952")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(
        depends=[
            "test_upgrade_process",
            "test_cdiconfig_scratch_overriden_before_upgrade",
        ]
    )
    def test_cdiconfig_scratch_preserved_after_upgrade(
        self,
        skip_if_not_override_cdiconfig_scratch_space,
        cdi_config,
        storage_class_for_updating_cdiconfig_scratch,
    ):
        """
        Check that the scratch StorageClass configuration should be preserved by the upgrade
        """
        expected_sc = (
            storage_class_for_updating_cdiconfig_scratch.instance.metadata.name
        )
        actual_sc = cdi_config.scratch_space_storage_class_from_status
        assert (
            actual_sc == expected_sc
        ), "The scratchSpaceStorageClass on CDIConfig config should not change after upgrade"

    @pytest.mark.polarion("CNV-5532")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(
        depends=[
            "test_upgrade_process",
            "test_install_ovs_with_annotations_before_upgrade",
        ]
    )
    def test_ovs_installed_with_annotations_after_upgrade(
        self,
        admin_client,
        ovs_daemonset,
        hyperconverged_ovs_annotations_fetched,
        network_addons_config,
    ):
        # Verify ovs opt-in still applies after upgrade
        verify_ovs_installed_with_annotations(
            admin_client=admin_client,
            ovs_daemonset=ovs_daemonset,
            hyperconverged_ovs_annotations_fetched=hyperconverged_ovs_annotations_fetched,
            network_addons_config=network_addons_config,
        )
