import shlex

import pytest
from netaddr import IPNetwork
from resources.utils import TimeoutSampler

from tests.network.l2_bridge.conftest import DHCP_IP_RANGE_START
from utilities.infra import BUG_STATUS_CLOSED
from utilities.network import assert_ping_successful, get_vmi_ip_v4_by_name


CUSTOM_ETH_PROTOCOL = "0x88B6"  # rfc5342 Local Experimental Ethertype. Used to test custom eth type and linux bridge


@pytest.mark.usefixtures("skip_rhel7_workers")
class TestL2LinuxBridge:
    """
    Test L2 connectivity via linux bridge CNI plugin.
    The main goal is to make sure that different kinds of L2 traffic can pass
    transparently via Linux Bridge.
    """

    @pytest.mark.parametrize(
        "dst_ip",
        [
            pytest.param(
                "l2_bridge_running_vm_b.dot1q_ip",
                marks=(
                    pytest.mark.polarion("CNV-2277"),
                    pytest.mark.bugzilla(
                        1754283,
                        skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED,
                    ),
                ),
            ),
            pytest.param(
                "l2_bridge_running_vm_b.mpls_local_ip",
                marks=(pytest.mark.polarion("CNV-2285")),
            ),
        ],
        ids=["dot1q", "mpls"],
    )
    def test_connectivity_l2_bridge(
        self,
        skip_if_no_multinic_nodes,
        namespace,
        dst_ip,
        configured_l2_bridge_vm_a,
        l2_bridge_running_vm_b,
    ):
        """
        Test VM to VM connectivity via dot1q/mpls
        """
        assert_ping_successful(src_vm=l2_bridge_running_vm_b, dst_ip=eval(dst_ip))

    @pytest.mark.polarion("CNV-2282")
    def test_dhcp_broadcast(
        self,
        skip_if_no_multinic_nodes,
        configured_l2_bridge_vm_a,
        l2_bridge_running_vm_b,
        dhcp_client_eth3_nm_connection_name,
        dhcp_nad,
    ):
        """
        Test broadcast traffic via L2 linux bridge. VM_A has dhcp server installed. VM_B dhcp client.
        """
        # Start dhcp client in l2_bridge_running_vm_b
        with l2_bridge_running_vm_b.ssh_exec.executor().session() as ssh_session:
            ssh_session.run_cmd(
                cmd=shlex.split(
                    f"sudo nmcli connection modify '{dhcp_client_eth3_nm_connection_name}' ipv4.method auto"
                )
            )
            ssh_session.run_cmd(
                cmd=shlex.split(
                    f"sudo nmcli connection up '{dhcp_client_eth3_nm_connection_name}'"
                )
            )
            ssh_session.run_cmd(
                cmd=shlex.split("sudo systemctl restart qemu-guest-agent.service")
            )

        current_ip = TimeoutSampler(
            timeout=120,
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
        out = configured_l2_bridge_vm_a.ssh_exec.run_command(
            command=shlex.split(
                f"nping -e eth2 --ether-type {CUSTOM_ETH_PROTOCOL} {dst_ip} -c {num_of_packets} &"
            )
        )[1]
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
