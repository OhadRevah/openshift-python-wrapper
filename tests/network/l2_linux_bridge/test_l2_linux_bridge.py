import contextlib
import pytest

from tests.network.utils import get_vmi_ip_by_name, run_test_connectivity
from utilities.console import Fedora
from resources.utils import TimeoutSampler

CUSTOM_ETH_PROTOCOL = (
    "0x88B6"
)  # rfc5342 Local Experimental Ethertype. Used to test custom eth type and linux bridge


@contextlib.contextmanager
def _open_console(vm):
    with Fedora(vm=vm.name, namespace=vm.namespace) as vm_console:
        yield vm_console


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
                "configured_vm_b.dot1q_ip", marks=(pytest.mark.polarion("CNV-2277"))
            ),
            pytest.param(
                "configured_vm_b.mpls_local_ip",
                marks=(pytest.mark.polarion("CNV-2285")),
            ),
        ],
        ids=["dot1q", "mpls"],
    )
    def test_connectivity_l2_bridge(
        self, namespace, dst_ip, configured_vm_a, configured_vm_b
    ):
        """
        Test VM to VM connectivity via dot1q/mpls
        """
        run_test_connectivity(
            src_vm=configured_vm_a.name,
            dst_vm=configured_vm_b.name,
            dst_ip=eval(dst_ip),
            positive=True,
            namespace=namespace.name,
        )

    @pytest.mark.polarion("CNV-2282")
    def test_dhcp_broadcast(self, configured_vm_a, configured_vm_b, dhcp_nad):
        """
        Test broadcast traffic via L2 linux bridge. VM_A has dhcp server installed. VM_B dhcp client.
        """

        current_ip = TimeoutSampler(
            timeout=60,
            sleep=2,
            func=get_vmi_ip_by_name,
            vmi=configured_vm_b.vmi,
            name=dhcp_nad.name,
        )
        for address in current_ip:
            if str(address) == configured_vm_b.dhcp_pool_address:
                return True

    @pytest.mark.polarion("CNV-2284")
    def test_custom_eth_type(
        self, configured_vm_a, configured_vm_b, custom_eth_type_llpd_nad
    ):
        """
        Test custom type field in ethernet header.
        """
        with _open_console(configured_vm_b) as vmb_console:
            vmb_console.sendline(
                f"sudo tcpdump -i eth2 -nn -e -c 5  ether proto {CUSTOM_ETH_PROTOCOL}"
            )

            with _open_console(configured_vm_a) as vma_console:
                vma_console.sendline(
                    f"sudo nping -e eth2 --ether-type {CUSTOM_ETH_PROTOCOL} "
                    f"{get_vmi_ip_by_name(configured_vm_b.vmi, custom_eth_type_llpd_nad.name)} -c 10"
                )
                vma_console.expect(
                    "[1]"
                )  #: Expected output. This is OK signal from nping
            vmb_console.expect(CUSTOM_ETH_PROTOCOL)

    @pytest.mark.polarion("CNV-2283")
    @pytest.mark.xfail(reason="https://github.com/kubevirt/kubevirt/issues/2292")
    def test_lldp_multicast(self, configured_vm_a, configured_vm_b):
        """
        Test multicast traffic via L2 linux bridge. LLDP protocol is used for the test. LLDP server installed in both
        VMs
        """
        with _open_console(configured_vm_a) as vma_console:
            vma_console.sendline("sudo lldptool -t -n -i eth2")
            vma_console.expect(f"Linux {configured_vm_b.name}")
