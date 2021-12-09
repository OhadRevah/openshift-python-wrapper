import logging
from ipaddress import ip_interface

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.virtual_machine_instance import VirtualMachineInstance
from ocp_resources.virtual_machine_restore import VirtualMachineRestore

import tests.install_upgrade_operators.product_upgrade.utils as upgrade_utils
from utilities import console
from utilities.constants import KMP_ENABLED_LABEL, KMP_VM_ASSIGNMENT_LABEL, LS_COMMAND
from utilities.exceptions import ResourceValueError
from utilities.infra import validate_nodes_ready, validate_nodes_schedulable
from utilities.network import (
    assert_ping_successful,
    get_vmi_ip_v4_by_name,
    get_vmi_mac_address_by_iface_name,
    verify_ovs_installed_with_annotations,
)
from utilities.storage import (
    assert_disk_serial,
    assert_hotplugvolume_nonexist_optional_restart,
    run_command_on_cirros_vm_and_check_output,
    wait_for_vm_volume_ready,
)
from utilities.virt import migrate_vm_and_verify, vm_console_run_commands


LOGGER = logging.getLogger(__name__)


@pytest.mark.upgrade
@pytest.mark.usefixtures(
    "skip_when_one_node",
    "cnv_upgrade_path",
    "nodes_taints_before_upgrade",
    "nodes_labels_before_upgrade",
    "base_templates",
)
class TestUpgrade:
    @pytest.mark.polarion("CNV-2974")
    @pytest.mark.order(before="test_upgrade_process")
    @pytest.mark.dependency(name="test_is_vm_running_before_upgrade")
    def test_is_vm_running_before_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            assert vm.vmi.status == VirtualMachineInstance.Status.RUNNING

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
        upgrade_utils.verify_vms_ssh_connectivity(vms_list=vms_for_upgrade)

    @pytest.mark.polarion("CNV-6999")
    @pytest.mark.order(before="test_upgrade_process")
    @pytest.mark.dependency(name="test_vm_run_strategy_before_upgrade")
    def test_vm_run_strategy_before_upgrade(
        self,
        manual_run_strategy_vm,
        always_run_strategy_vm,
        running_manual_run_strategy_vm,
        running_always_run_strategy_vm,
    ):
        upgrade_utils.verify_vms_ssh_connectivity(
            vms_list=[manual_run_strategy_vm, always_run_strategy_vm]
        )

    @pytest.mark.polarion("CNV-7243")
    @pytest.mark.order(before="test_upgrade_process")
    @pytest.mark.dependency(name="test_windows_vm_before_upgrade")
    def test_windows_vm_before_upgrade(
        self,
        windows_vm,
    ):
        upgrade_utils.verify_vms_ssh_connectivity(vms_list=[windows_vm])

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
        network_addons_config_scope_session,
        hyperconverged_ovs_annotations_enabled_scope_class,
        hyperconverged_ovs_annotations_fetched,
    ):
        # Verify ovs annotation has been enabled (opt-in)
        assert (
            hyperconverged_ovs_annotations_fetched
        ), "OVS hasn't been opt-in as needed."

    @pytest.mark.polarion("CNV-5993")
    @pytest.mark.order(before="test_upgrade_process")
    @pytest.mark.dependency(name="test_vm_snapshot_restore_before_upgrade")
    def test_vm_snapshot_restore_before_upgrade(
        self,
        cirros_vm_for_upgrade_a,
        snapshots_for_upgrade_a,
    ):
        with VirtualMachineRestore(
            name=f"restore-snapshot-{cirros_vm_for_upgrade_a.name}",
            namespace=snapshots_for_upgrade_a.namespace,
            vm_name=cirros_vm_for_upgrade_a.name,
            snapshot_name=snapshots_for_upgrade_a.name,
        ) as vm_restore:
            vm_restore.wait_complete()
            cirros_vm_for_upgrade_a.start(wait=True)
            run_command_on_cirros_vm_and_check_output(
                vm=cirros_vm_for_upgrade_a,
                command=LS_COMMAND,
                expected_result="1",
            )

    @pytest.mark.polarion("CNV-5995")
    @pytest.mark.order(before="test_upgrade_process")
    @pytest.mark.dependency(name="test_vm_snapshot_created_before_upgrade")
    def test_vm_snapshot_created_before_upgrade(
        self,
        snapshots_for_upgrade_b,
    ):
        assert snapshots_for_upgrade_b.instance.status.readyToUse

    @pytest.mark.polarion("CNV-7258")
    @pytest.mark.order(before="test_upgrade_process")
    @pytest.mark.dependency(name="test_vm_with_hotplug_before_upgrade")
    def test_vm_with_hotplug_before_upgrade(
        self,
        namespace,
        blank_disk_dv_with_default_sc,
        fedora_vm_for_hotplug_upg,
        hotplug_volume_upg,
    ):
        wait_for_vm_volume_ready(vm=fedora_vm_for_hotplug_upg)
        assert_disk_serial(vm=fedora_vm_for_hotplug_upg)
        assert_hotplugvolume_nonexist_optional_restart(
            vm=fedora_vm_for_hotplug_upg, restart=True
        )

    @pytest.mark.polarion("CNV-7343")
    @pytest.mark.order(before="test_upgrade_process")
    @pytest.mark.dependency(name="test_vm_connectivity_with_macspoofing_before_upgrade")
    def test_vm_connectivity_with_macspoofing_before_upgrade(
        self,
        vma_upgrade_mac_spoof,
        vmb_upgrade_mac_spoof,
        running_vma_upgrade_mac_spoof,
        running_vmb_upgrade_mac_spoof,
    ):
        """
        Added test to verify ping works when macspoof is set.
        Adding field should not break existing tests. However this test will not work if nftables are missing.
        """
        assert_ping_successful(
            src_vm=vma_upgrade_mac_spoof,
            dst_ip=get_vmi_ip_v4_by_name(
                vm=vmb_upgrade_mac_spoof,
                name=vmb_upgrade_mac_spoof.interfaces[0],
            ),
        )

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
        cnv_target_version,
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
                cnv_target_version=cnv_target_version,
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
    def test_nodes_ready_after_upgrade(self, nodes):
        LOGGER.info("Verify all nodes are in ready state after upgrade")
        validate_nodes_ready(nodes=nodes)

    @pytest.mark.polarion("CNV-6865")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(depends=["test_upgrade_process"])
    def test_nodes_schedulable_after_upgrade(
        self,
        nodes,
    ):
        LOGGER.info("Verify all nodes are in schedulable state after upgrade")
        validate_nodes_schedulable(nodes=nodes)

    @pytest.mark.polarion("CNV-6866")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(depends=["test_upgrade_process"])
    def test_nodes_taints_after_upgrade(
        self, admin_client, nodes, nodes_taints_before_upgrade
    ):
        LOGGER.info("Verify nodes taints after upgrade.")
        upgrade_utils.verify_nodes_taints_after_upgrade(
            nodes=nodes, nodes_taints_before_upgrade=nodes_taints_before_upgrade
        )

    @pytest.mark.polarion("CNV-6924")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(depends=["test_upgrade_process"])
    def test_nodes_labels_after_upgrade(
        self, admin_client, nodes, nodes_labels_before_upgrade
    ):
        LOGGER.info("Verify nodes labels after upgrade.")
        upgrade_utils.verify_nodes_labels_after_upgrade(
            nodes=nodes, nodes_labels_before_upgrade=nodes_labels_before_upgrade
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
        upgrade_utils.verify_vms_ssh_connectivity(vms_list=vms_for_upgrade)

    @pytest.mark.polarion("CNV-7000")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(
        depends=["test_upgrade_process", "test_vm_run_strategy_before_upgrade"]
    )
    def test_vm_run_strategy_after_upgrade(
        self, manual_run_strategy_vm, always_run_strategy_vm
    ):
        upgrade_utils.verify_vms_ssh_connectivity(
            vms_list=[manual_run_strategy_vm, always_run_strategy_vm]
        )

    @pytest.mark.polarion("CNV-7244")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(
        depends=["test_upgrade_process", "test_windows_vm_before_upgrade"]
    )
    def test_windows_vm_after_upgrade(
        self,
        windows_vm,
    ):
        upgrade_utils.verify_vms_ssh_connectivity(vms_list=[windows_vm])

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
        network_addons_config_scope_session,
    ):
        # Verify ovs opt-in still applies after upgrade
        verify_ovs_installed_with_annotations(
            admin_client=admin_client,
            ovs_daemonset=ovs_daemonset,
            hyperconverged_ovs_annotations_fetched=hyperconverged_ovs_annotations_fetched,
            network_addons_config=network_addons_config_scope_session,
        )

    @pytest.mark.polarion("CNV-5932")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(
        depends=[
            "test_is_vm_running_after_upgrade",
        ]
    )
    def test_vmi_pod_image_updates_after_upgrade_optin(
        self,
        unupdated_vmi_pods_names,
    ):
        """
        Check that the VMI Pods use the latest images after the upgrade
        """
        assert (
            not unupdated_vmi_pods_names
        ), f"The following VMI Pods were not updated: {unupdated_vmi_pods_names}"

    @pytest.mark.polarion("CNV-5994")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(
        depends=["test_upgrade_process", "test_vm_snapshot_restore_before_upgrade"]
    )
    def test_vm_snapshot_restore_check_after_upgrade(
        self,
        cirros_vm_for_upgrade_a,
    ):
        run_command_on_cirros_vm_and_check_output(
            vm=cirros_vm_for_upgrade_a,
            command=LS_COMMAND,
            expected_result="1",
        )

    @pytest.mark.polarion("CNV-5996")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(
        depends=["test_upgrade_process", "test_vm_snapshot_created_before_upgrade"]
    )
    def test_vm_snapshot_restore_create_after_upgrade(
        self, cirros_vm_for_upgrade_b, snapshots_for_upgrade_b
    ):
        with VirtualMachineRestore(
            name=f"restore-snapshot-{cirros_vm_for_upgrade_b.name}",
            namespace=snapshots_for_upgrade_b.namespace,
            vm_name=cirros_vm_for_upgrade_b.name,
            snapshot_name=snapshots_for_upgrade_b.name,
        ) as vm_restore:
            vm_restore.wait_complete()
            cirros_vm_for_upgrade_b.start(wait=True)
            run_command_on_cirros_vm_and_check_output(
                vm=cirros_vm_for_upgrade_b,
                command=LS_COMMAND,
                expected_result="1",
            )

    @pytest.mark.polarion("CNV-5310")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(
        depends=[
            "test_upgrade_process",
            "test_vm_with_hotplug_before_upgrade",
        ]
    )
    def test_vm_with_hotplug_after_upgrade(
        self,
        namespace,
        blank_disk_dv_with_default_sc,
        fedora_vm_for_hotplug_upg,
        hotplug_volume_upg,
    ):
        assert_disk_serial(vm=fedora_vm_for_hotplug_upg)
        assert_hotplugvolume_nonexist_optional_restart(vm=fedora_vm_for_hotplug_upg)

    @pytest.mark.polarion("CNV-7402")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(
        depends=[
            "test_upgrade_process",
            "test_vm_connectivity_with_macspoofing_before_upgrade",
        ]
    )
    def test_vm_connectivity_with_macspoofing_after_upgrade(
        self,
        vma_upgrade_mac_spoof,
        vmb_upgrade_mac_spoof,
    ):
        """
        Added test to verify ping works when macspoof is set.
        After upgrade, adding macspoofing in NAD should not make ping test to failed.
        This test is expected to fail if nftables are missing after upgrade.
        """
        assert_ping_successful(
            src_vm=vma_upgrade_mac_spoof,
            dst_ip=get_vmi_ip_v4_by_name(
                vm=vmb_upgrade_mac_spoof,
                name=vmb_upgrade_mac_spoof.interfaces[0],
            ),
        )

    @pytest.mark.polarion("CNV-5749")
    @pytest.mark.order(after="test_upgrade_process")
    @pytest.mark.dependency(depends=["test_upgrade_process"])
    def test_golden_image_pvc_names_after_upgrade(
        self, base_templates, base_templates_after_upgrade
    ):
        LOGGER.info(
            f"Comparing default value for parameter {upgrade_utils.SRC_PVC_NAME} "
            f"in base templates before and after upgrade"
        )
        mismatching_templates = upgrade_utils.mismatching_src_pvc_names(
            pre_upgrade_templates=base_templates,
            post_upgrade_templates=base_templates_after_upgrade,
        )

        if mismatching_templates:
            raise ResourceValueError(
                f"Golden image default {upgrade_utils.SRC_PVC_NAME} "
                f"mismatch after upgrade:\n{mismatching_templates}"
            )
