"""
VM to VM connectivity
"""
from ipaddress import ip_interface

import pytest
import tests.network.utils as network_utils


@pytest.mark.polarion("CNV-3296")
def test_connectivity_over_pod_network(
    skip_when_one_node, skip_when_no_bond, disconnected_slave, running_vma, running_vmb,
):
    """
    Check connectivity
    """
    vma_ip = running_vma.vmi.interfaces[0]["ipAddress"]
    vmb_ip = running_vmb.vmi.interfaces[0]["ipAddress"]
    for vm, ip in zip([running_vma, running_vmb], [vmb_ip, vma_ip]):

        network_utils.assert_ping_successful(
            src_vm=vm, dst_ip=ip_interface(ip).ip,
        )
