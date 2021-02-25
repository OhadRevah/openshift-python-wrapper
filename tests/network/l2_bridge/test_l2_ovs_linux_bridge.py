import shlex

import pytest
from netaddr import IPNetwork
from resources.utils import TimeoutSampler

from tests.network.l2_bridge.conftest import DHCP_IP_RANGE_START
from utilities.infra import run_ssh_commands
from utilities.network import assert_ping_successful, get_vmi_ip_v4_by_name


CUSTOM_ETH_PROTOCOL = "0x88B6"  # rfc5342 Local Experimental Ethertype. Used to test custom eth type and linux bridge


@pytest.mark.usefixtures("skip_rhel7_workers")
class TestL2LinuxBridge:
    """
    Test L2 connectivity via linux bridge CNI plugin.
    The main goal is to make sure that different kinds of L2 traffic can pass
    transparently via Linux Bridge.
    """

    @pytest.mark.polarion("CNV-2285")
    def test_connectivity_l2_bridge(
        self,
        skip_if_no_multinic_nodes,
        namespace,
        configured_l2_bridge_vm_a,
        l2_bridge_running_vm_b,
    ):
        """
        Test VM to VM connectivity via mpls
        """
        assert_ping_successful(
            src_vm=l2_bridge_running_vm_b, dst_ip=l2_bridge_running_vm_b.mpls_local_ip
        )

    @pytest.mark.polarion("CNV-2282")
    def test_dhcp_broadcast(
        self,
        skip_if_no_multinic_nodes,
        configured_l2_bridge_vm_a,
        l2_bridge_running_vm_b,
        dhcp_nad,
        started_vmb_dhcp_client,
    ):
        """
        Test broadcast traffic via L2 linux bridge. VM_A has dhcp server installed. VM_B dhcp client.
        """
        current_ip = TimeoutSampler(
            wait_timeout=120,
            sleep=2,
            func=get_vmi_ip_v4_by_name,
            vmi=l2_bridge_running_vm_b.vmi,
            name=dhcp_nad.name,
        )
        for address in current_ip:
            if str(address) in IPNetwork(f"{DHCP_IP_RANGE_START}/24"):
                return True

    @pytest.mark.polarion("CNV-2284")
    def test_custom_eth_type(
        self,
        skip_if_no_multinic_nodes,
        configured_l2_bridge_vm_a,
        l2_bridge_running_vm_b,
        custom_eth_type_llpd_nad,
    ):
        """
        Test custom type field in ethernet header.
        """
        num_of_packets = 10
        dst_ip = get_vmi_ip_v4_by_name(
            vmi=l2_bridge_running_vm_b.vmi, name=custom_eth_type_llpd_nad.name
        )
        out = run_ssh_commands(
            host=configured_l2_bridge_vm_a.ssh_exec,
            commands=[
                shlex.split(
                    f"nping -e eth2 --ether-type {CUSTOM_ETH_PROTOCOL} {dst_ip} -c {num_of_packets} &"
                )
            ],
        )[0]
        assert f"Successful connections: {num_of_packets}" in out

    @pytest.mark.polarion("CNV-2674")
    def test_icmp_multicast(
        self,
        skip_if_no_multinic_nodes,
        namespace,
        configured_l2_bridge_vm_a,
        l2_bridge_running_vm_b,
    ):
        """
        Test multicast traffic(ICMP) via linux bridge
        """
        assert_ping_successful(src_vm=l2_bridge_running_vm_b, dst_ip="224.0.0.1")
