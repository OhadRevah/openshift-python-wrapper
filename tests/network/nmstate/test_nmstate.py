import logging
from ipaddress import ip_interface

import pytest
from tests.network.utils import assert_ping_successful


LOGGER = logging.getLogger(__name__)
REMOTE_IP = "8.8.8.8"

pytestmark = pytest.mark.skip("Test kill the cluster, need investigation")


@pytest.mark.usefixtures("skip_rhel7_workers")
class TestWithDhcpOverBridge:
    @pytest.mark.polarion("CNV-3002")
    def test_ping_between_vms_through_brext(
        self,
        skip_when_one_node,
        network_utility_pods,
        bridges_on_management_ifaces,
        vma,
        vmb,
        running_vma,
        running_vmb,
    ):
        assert_ping_successful(
            src_vm=running_vma,
            dst_ip=ip_interface(running_vmb.vmi.interfaces[0]["ipAddress"]).ip,
        )

    @pytest.mark.polarion("CNV-3003")
    def test_ping_remote_ip_through_brext(
        self,
        skip_when_one_node,
        bridges_on_management_ifaces,
        vma,
        vmb,
        running_vma,
        running_vmb,
    ):
        assert_ping_successful(src_vm=running_vma, dst_ip=REMOTE_IP)
        assert_ping_successful(src_vm=running_vmb, dst_ip=REMOTE_IP)


# Test class should be run as last, because it should check connectivity after,
# bridge was created, got dhcp of management and release it back to the port
@pytest.mark.last
@pytest.mark.usefixtures("skip_rhel7_workers")
class TestAfterBridgeTeardown:
    @pytest.mark.polarion("CNV-3028")
    def test_ping_between_vms_through_main_interface(
        self, skip_when_one_node, vma, vmb, running_vma, running_vmb
    ):
        assert_ping_successful(
            src_vm=running_vma,
            dst_ip=ip_interface(running_vmb.vmi.interfaces[0]["ipAddress"]).ip,
        )

    @pytest.mark.polarion("CNV-3029")
    def test_ping_remote_ip_through_main_interface(
        self, skip_when_one_node, vma, vmb, running_vma, running_vmb
    ):
        assert_ping_successful(src_vm=running_vma, dst_ip=REMOTE_IP)
        assert_ping_successful(src_vm=running_vmb, dst_ip=REMOTE_IP)
