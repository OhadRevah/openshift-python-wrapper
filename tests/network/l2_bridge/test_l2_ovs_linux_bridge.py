import contextlib

import pytest
from netaddr import IPNetwork
from resources.utils import TimeoutSampler

from tests.network.l2_bridge.conftest import DHCP_IP_RANGE_START
from utilities import console
from utilities.console import Fedora
from utilities.infra import BUG_STATUS_CLOSED
from utilities.network import assert_ping_successful, get_vmi_ip_v4_by_name
from utilities.virt import vm_console_run_commands


CUSTOM_ETH_PROTOCOL = "0x88B6"  # rfc5342 Local Experimental Ethertype. Used to test custom eth type and linux bridge


@contextlib.contextmanager
def _open_console(vm):
    with Fedora(vm=vm) as vm_console:
        yield vm_console


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
                "configured_l2_bridge_vm_b.dot1q_ip",
                marks=(
                    pytest.mark.polarion("CNV-2277"),
                    pytest.mark.bugzilla(
                        1754283,
                        skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED,
                    ),
                ),
            ),
            pytest.param(
                "configured_l2_bridge_vm_b.mpls_local_ip",
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
        configured_l2_bridge_vm_b,
    ):
        """
        Test VM to VM connectivity via dot1q/mpls
        """
        assert_ping_successful(src_vm=configured_l2_bridge_vm_b, dst_ip=eval(dst_ip))

    @pytest.mark.polarion("CNV-2282")
    def test_dhcp_broadcast(
        self,
        skip_if_no_multinic_nodes,
        configured_l2_bridge_vm_a,
        configured_l2_bridge_vm_b,
        dhcp_client_eth3_nm_connection_name,
        dhcp_nad,
    ):
        """
        Test broadcast traffic via L2 linux bridge. VM_A has dhcp server installed. VM_B dhcp client.
        """
        # Start dhcp client in configured_l2_bridge_vm_b
        post_install_command = [
            f"sudo nmcli connection modify '{dhcp_client_eth3_nm_connection_name}' ipv4.method auto",
            f"sudo nmcli connection up '{dhcp_client_eth3_nm_connection_name}'",
            "sudo systemctl restart qemu-guest-agent.service",  # Force guest agent to report the new IP.
        ]
        vm_console_run_commands(
            console_impl=console.Fedora,
            vm=configured_l2_bridge_vm_b,
            commands=post_install_command,
        )

        current_ip = TimeoutSampler(
            timeout=120,
            sleep=2,
            func=get_vmi_ip_v4_by_name,
            vmi=configured_l2_bridge_vm_b.vmi,
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
        configured_l2_bridge_vm_b,
        custom_eth_type_llpd_nad,
    ):
        """
        Test custom type field in ethernet header.
        """
        with _open_console(vm=configured_l2_bridge_vm_b) as vmb_console:
            vmb_console.sendline(
                f"sudo tcpdump -i eth2 -nn -e -c 5  ether proto {CUSTOM_ETH_PROTOCOL}"
            )

            with _open_console(vm=configured_l2_bridge_vm_a) as vma_console:
                vma_console.sendline(
                    f"sudo nping -e eth2 --ether-type {CUSTOM_ETH_PROTOCOL} "
                    f"{get_vmi_ip_v4_by_name(configured_l2_bridge_vm_b.vmi, custom_eth_type_llpd_nad.name)} -c 10"
                )
                vma_console.expect(
                    "[1]"
                )  #: Expected output. This is OK signal from nping
            vmb_console.expect(CUSTOM_ETH_PROTOCOL)

    @pytest.mark.polarion("CNV-2674")
    def test_icmp_multicast(
        self,
        skip_if_no_multinic_nodes,
        namespace,
        configured_l2_bridge_vm_a,
        configured_l2_bridge_vm_b,
    ):
        """
        Test multicast traffic(ICMP) via linux bridge
        """
        assert_ping_successful(src_vm=configured_l2_bridge_vm_b, dst_ip="224.0.0.1")