import logging
import os
from ipaddress import ip_interface

import pytest
from ocp_resources.utils import TimeoutSampler

from tests.network.upgrade.utils import (
    assert_bridge_and_vms_on_same_node,
    assert_nmstate_bridge_creation,
    assert_node_is_marked_by_bridge,
)
from tests.network.utils import assert_authentication_request
from tests.upgrade_params import (
    IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
    IUO_UPGRADE_TEST_ORDERING_NODE_ID,
)
from utilities.constants import (
    DEPENDENCY_SCOPE_SESSION,
    KMP_ENABLED_LABEL,
    KMP_VM_ASSIGNMENT_LABEL,
    TIMEOUT_10SEC,
)
from utilities.network import (
    assert_ping_successful,
    get_vmi_ip_v4_by_name,
    get_vmi_mac_address_by_iface_name,
    verify_ovs_installed_with_annotations,
)


LOGGER = logging.getLogger(__name__)
DEPENDENCIES_NODE_ID_PREFIX = f"{os.path.abspath(__file__)}::TestUpgradeNetwork"


pytestmark = pytest.mark.usefixtures("skip_when_one_node")


@pytest.mark.upgrade
class TestUpgradeNetwork:
    """Pre-upgrade tests"""

    @pytest.mark.polarion("CNV-2743")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        name=f"{DEPENDENCIES_NODE_ID_PREFIX}::test_nmstate_bridge_before_upgrade"
    )
    def test_nmstate_bridge_before_upgrade(self, bridge_on_one_node):
        assert_nmstate_bridge_creation(bridge=bridge_on_one_node)

    @pytest.mark.polarion("CNV-2744")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        name=f"{DEPENDENCIES_NODE_ID_PREFIX}::test_bridge_marker_before_upgrade"
    )
    def test_bridge_marker_before_upgrade(
        self,
        vm_upgrade_a,
        vm_upgrade_b,
        running_vm_upgrade_a,
        running_vm_upgrade_b,
        upgrade_bridge_marker_nad,
        bridge_on_one_node,
    ):
        assert_bridge_and_vms_on_same_node(
            vm_a=running_vm_upgrade_a,
            vm_b=running_vm_upgrade_b,
            bridge=bridge_on_one_node,
        )
        assert_node_is_marked_by_bridge(
            bridge_nad=upgrade_bridge_marker_nad, vm=running_vm_upgrade_b
        )

    @pytest.mark.polarion("CNV-2750")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        name=f"{DEPENDENCIES_NODE_ID_PREFIX}::test_linux_bridge_before_upgrade"
    )
    def test_linux_bridge_before_upgrade(
        self,
        vm_upgrade_a,
        vm_upgrade_b,
        running_vm_upgrade_a,
        running_vm_upgrade_b,
        upgrade_bridge_marker_nad,
        bridge_on_one_node,
    ):
        dst_ip_address = None
        sampler = TimeoutSampler(
            wait_timeout=TIMEOUT_10SEC,
            sleep=1,
            func=lambda: running_vm_upgrade_b.vmi.instance.status.interfaces[
                1
            ].ipAddress,
        )
        for sample in sampler:
            if sample:
                dst_ip_address = ip_interface(address=sample).ip
                break
        assert_ping_successful(src_vm=running_vm_upgrade_a, dst_ip=str(dst_ip_address))

    @pytest.mark.polarion("CNV-5944")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        name=f"{DEPENDENCIES_NODE_ID_PREFIX}::test_kubemacpool_enabled_ns_before_upgrade"
    )
    def test_kubemacpool_enabled_ns_before_upgrade(
        self,
        kmp_vm_label,
    ):
        # KubeMacPool is enabled in namespace.
        assert kmp_vm_label.get(KMP_VM_ASSIGNMENT_LABEL) == KMP_ENABLED_LABEL

    @pytest.mark.polarion("CNV-2745")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        name=f"{DEPENDENCIES_NODE_ID_PREFIX}::test_kubemacpool_before_upgrade"
    )
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

    @pytest.mark.polarion("CNV-5659")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        name=f"{DEPENDENCIES_NODE_ID_PREFIX}::test_install_ovs_with_annotations_before_upgrade"
    )
    def test_install_ovs_with_annotations_before_upgrade(
        self,
        admin_client,
        hco_namespace,
        hyperconverged_resource_scope_session,
        network_addons_config_scope_session,
        hyperconverged_ovs_annotations_enabled_scope_session,
        hyperconverged_ovs_annotations_fetched,
    ):
        # Verify ovs annotation has been enabled (opt-in)
        assert (
            hyperconverged_ovs_annotations_fetched
        ), "OVS hasn't been opt-in as needed."

    @pytest.mark.polarion("CNV-7343")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        name=f"{DEPENDENCIES_NODE_ID_PREFIX}::test_vm_connectivity_with_macspoofing_before_upgrade"
    )
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

    @pytest.mark.polarion("CNV-5915")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        name=f"{DEPENDENCIES_NODE_ID_PREFIX}::test_vm_connectivity_to_mesh_before_upgrade"
    )
    def test_vm_connectivity_to_mesh_before_upgrade(
        self,
        vm_cirros_with_service_mesh_annotation_for_upgrade,
        httpbin_service_mesh_service_for_upgrade,
        service_mesh_vm_for_upgrade_with_console_ready,
    ):
        assert_authentication_request(
            vm=vm_cirros_with_service_mesh_annotation_for_upgrade,
            service=httpbin_service_mesh_service_for_upgrade.app_name,
        )

    """ Post-upgrade tests """

    @pytest.mark.polarion("CNV-2747")
    @pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{DEPENDENCIES_NODE_ID_PREFIX}::test_nmstate_bridge_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_nmstate_bridge_after_upgrade(self, bridge_on_one_node):
        assert_nmstate_bridge_creation(bridge=bridge_on_one_node)

    @pytest.mark.polarion("CNV-2749")
    @pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{DEPENDENCIES_NODE_ID_PREFIX}::test_bridge_marker_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
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
        assert_bridge_and_vms_on_same_node(
            vm_a=running_vm_upgrade_a,
            vm_b=running_vm_upgrade_b,
            bridge=bridge_on_one_node,
        )
        assert_node_is_marked_by_bridge(
            bridge_nad=upgrade_bridge_marker_nad, vm=running_vm_upgrade_b
        )

    @pytest.mark.polarion("CNV-2748")
    @pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{DEPENDENCIES_NODE_ID_PREFIX}::test_linux_bridge_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
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
    @pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{DEPENDENCIES_NODE_ID_PREFIX}::test_kubemacpool_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
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
    @pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{DEPENDENCIES_NODE_ID_PREFIX}::test_kubemacpool_enabled_ns_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_kubemacpool_enabled_ns_after_upgrade(
        self,
        kmp_vm_label,
    ):
        # KubeMacPool is still enabled in namespace.
        assert kmp_vm_label.get(KMP_VM_ASSIGNMENT_LABEL) == KMP_ENABLED_LABEL

    @pytest.mark.polarion("CNV-5532")
    @pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{DEPENDENCIES_NODE_ID_PREFIX}::test_install_ovs_with_annotations_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
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

    @pytest.mark.polarion("CNV-7402")
    @pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{DEPENDENCIES_NODE_ID_PREFIX}::test_vm_connectivity_with_macspoofing_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
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

    @pytest.mark.polarion("CNV-7346")
    @pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{DEPENDENCIES_NODE_ID_PREFIX}::test_vm_connectivity_to_mesh_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_vm_connectivity_to_mesh_after_upgrade(
        self,
        vm_cirros_with_service_mesh_annotation_for_upgrade,
        httpbin_service_mesh_service_for_upgrade,
        service_mesh_vm_for_upgrade_with_console_ready,
    ):
        assert_authentication_request(
            vm=vm_cirros_with_service_mesh_annotation_for_upgrade,
            service=httpbin_service_mesh_service_for_upgrade.app_name,
        )
