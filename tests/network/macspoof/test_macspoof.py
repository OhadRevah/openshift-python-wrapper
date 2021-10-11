import pytest

from tests.network.utils import assert_no_ping


@pytest.mark.polarion("CNV-7264")
def test_macspoof_prevent_connectivity(
    linux_bridge_attached_vma,
    linux_bridge_attached_vmb,
    linux_bridge_attached_running_vma,
    linux_bridge_attached_running_vmb,
    ping_vmb_from_vma,
    vma_interface_spoofed_mac,
    vmb_ip_address,
):
    assert_no_ping(src_vm=linux_bridge_attached_vma, dst_ip=vmb_ip_address)
