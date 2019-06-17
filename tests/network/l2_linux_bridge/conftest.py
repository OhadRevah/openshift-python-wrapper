# -*- coding: utf-8 -*-
from ipaddress import ip_interface
from pexpect.exceptions import TIMEOUT

import pytest

from resources.namespace import Namespace
from tests import utils
from tests.network.utils import Bridge, VXLANTunnel, bridge_nad
from tests.network.config import BRIDGE_BR1
from tests.utils import FedoraVirtualMachine
from utilities.console import Fedora

#: Test setup
#       .........                                                                                      ..........
#       |       |---eth1:192.168.0.1:                                              192.168.0.2:---eth1:|        |
#       |       |---eth1.10:192.168.1.1 :dot1q test :                            192.168.1.2:eth1.10---|        |
#       | VM-A  |---eth2:192.168.2.1    : multicast(LLDP), custom eth type test:    192.168.2.2:eth2---|  VM-B  |
#       |       |---eth3:192.168.3.1    : DHCP test :                               192.168.3.2:eth3---|        |
#       |.......|---eth4:192.168.4.1    : mpls test :                               192.168.4.2:eth4---|........|

VMA_MPLS_LOOPBACK_IP = "192.168.100.1/32"
VMA_MPLS_ROUTE_TAG = 100
VMB_MPLS_LOOPBACK_IP = "192.168.200.1/32"
VMB_MPLS_ROUTE_TAG = 200
VMB_DHCP_ADDRESS = "192.168.3.3"
DOT1Q_VLAN_ID = 10


class VirtualMachineAttachedToBridge(FedoraVirtualMachine):
    def __init__(self, name, namespace, interfaces, ip_addresses, cloud_init_cmd,
                 mpls_local_tag, mpls_local_ip, mpls_dest_ip,
                 mpls_dest_tag, mpls_route_next_hop, dhcp_pool_address):

        self.mpls_local_tag = mpls_local_tag
        self.ip_addresses = ip_addresses
        self.mpls_local_ip = ip_interface(mpls_local_ip).ip
        self.dhcp_pool_address = dhcp_pool_address
        cloud_init_script = (
            "\n#cloud-config\n"
            "password: fedora\n"
            "chpasswd: {expire: False}\n"
            "bootcmd:\n"
            "  - dnf install -y lldpad qemu-guest-agent kernel-modules-$(uname -r) nmap dhcp tcpdump\n"
            "  - systemctl start qemu-guest-agent\n"
            "  - nmcli con add type ethernet con-name eth1 ifname eth1\n"
            f"  - nmcli con mod eth1 ipv4.addresses {self.ip_addresses[0]}/24 ipv4.method manual\n"
            "  - nmcli con add type ethernet con-name eth2 ifname eth2\n"
            f"  - nmcli con mod eth2 ipv4.addresses {self.ip_addresses[1]}/24 ipv4.method manual\n"
            "  - nmcli con add type ethernet con-name eth3 ifname eth3\n"
            f"  - nmcli con mod eth3 ipv4.addresses {self.ip_addresses[2]}/24 ipv4.method manual\n"
            "  - nmcli con add type ethernet con-name eth4 ifname eth4\n"
            f"  - nmcli con mod eth4 ipv4.addresses {self.ip_addresses[3]}/24 ipv4.method manual\n"
            "  - nmcli conn add con-name VLAN_10 type vlan ifname eth1.10 ipv4.method manual ipv4.addresses "
            f"{self.ip_addresses[4]}/24 dev eth1 vlan.id {DOT1Q_VLAN_ID} ipv6.method ignore autoconnect true\n"
            "runcmd:\n"
            "  - sed -i s/'PasswordAuthentication no'/'PasswordAuthentication yes'/g /etc/ssh/sshd_config\n"
            "  - systemctl restart sshd\n"
            "  - modprobe mpls_router\n"  # In order to test mpls we need to load driver
            "  - sysctl -w net.mpls.platform_labels=1000\n"  # Activate mpls labeling feature
            "  - sysctl -w net.mpls.conf.eth4.input=1\n"  # Allow incoming mpls traffic
            "  - systemctl start lldpad\n"  # In order to test multicast traffic LLDP daemon is used
            "  - sysctl -w net.ipv4.conf.all.arp_ignore=1\n"   # 2 kernel flags are used to disable wrong arp behavior
            "  - sysctl -w net.ipv4.conf.all.arp_announce=2\n"  # Send arp reply only if ip belongs to the interface
            f"  - ip addr add {self.mpls_local_ip} dev lo\n"
            f"  - ip -f mpls route add {self.mpls_local_tag} dev lo\n"
            "  - nmcli connection up eth4\n"  # In order to add mpls route we need to make sure that connection is UP
            f"  - ip route add {mpls_dest_ip} encap mpls {mpls_dest_tag} via inet {mpls_route_next_hop}\n"
            "  - nmcli connection up eth2\n"
            "  - lldptool set-lldp -i eth2 adminStatus=rxtx\n"    # Allow to LLDP daemon to Receive/Transmit frames
            # To enable the broadcasting of some more LLDP key/value pairs:
            "  - lldptool -T -i eth2 -V sysName enableTx=yes\n"   # System Name TLV
            "  - lldptool -T -i eth2 -V portDesc enableTx=yes\n"  # Port Description TLV
            "  - lldptool -T -i eth2 -V sysDesc enableTx=yes\n"   # System Description TLV
            "  - lldptool -T -i eth2 -V sysCap enableTx=yes\n"    # System Capacity TLV
            "  - lldptool -T -i eth2 -V mngAddr enableTx=yes\n"    # Management Address
        ) + cloud_init_cmd

        networks = {}
        for network in interfaces:
            networks.update({network: network})

        super().__init__(
            name=name,
            namespace=namespace,
            interfaces=interfaces,
            networks=networks,
            cloud_init_user_data=cloud_init_script)

    @property
    def dot1q_ip(self):
        return self.ip_addresses[4]


def running_vmi(vm):
    assert vm.start(wait=True)
    assert vm.vmi.wait_until_running()
    return vm.vmi


class CommandExecFailed(Exception):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"Command: {self.name} - exec failed."


def run_commands(vmi, commands):
    """
    Run a list of commands inside VM and check all commands return 0.
    If return code other than 0 then it will break execution and raise exception.

    Args:
        vmi (obj): VirtualMachine instance
        commands (list): List of commands
    """
    with Fedora(
            vm=vmi.name,
            namespace=vmi.namespace) as vm_console:

        for command in commands:
            vm_console.sendline(command)
            vm_console.sendline("echo rc==$?==")      # This construction rc==$?== is unique. Return code validation
            try:
                vm_console.expect(r"rc==0==", timeout=60)  # Expected return code is 0
            except TIMEOUT:
                raise CommandExecFailed(command)


def bridge_attached_vm(
    name, namespace, interfaces, ip_addresses, mpls_local_tag,
    mpls_dest_ip, mpls_dest_tag, mpls_route_next_hop,
    mpls_local_ip, cloud_init_script="", dhcp_pool_address=""
):
    with VirtualMachineAttachedToBridge(
            namespace=namespace,
            name=name,
            interfaces=interfaces,
            ip_addresses=ip_addresses,
            cloud_init_cmd=cloud_init_script,
            mpls_local_tag=mpls_local_tag,
            mpls_local_ip=mpls_local_ip,
            dhcp_pool_address=dhcp_pool_address,
            mpls_dest_ip=mpls_dest_ip,
            mpls_dest_tag=mpls_dest_tag,
            mpls_route_next_hop=mpls_route_next_hop) as vm:
        yield vm


@pytest.fixture(scope='class')
def namespace():
    with Namespace(name='l2-bridge-ns') as ns:
        yield ns


@pytest.fixture(scope='class')
def dot1q_nad(namespace):
    with bridge_nad(namespace=namespace, name="dot1q", bridge=BRIDGE_BR1) as dot1q_nad:
        yield dot1q_nad


@pytest.fixture(scope='class')
def dhcp_nad(namespace):
    with bridge_nad(namespace=namespace, name="dhcp-broadcast", bridge=BRIDGE_BR1) as dhcp_broadcast:
        yield dhcp_broadcast


@pytest.fixture(scope='class')
def custom_eth_type_llpd_nad(namespace):
    with bridge_nad(namespace=namespace, name="custom-eth-type-lldp", bridge=BRIDGE_BR1) as custom_eth_type_lldp:
        yield custom_eth_type_lldp


@pytest.fixture(scope='class')
def mpls_nad(namespace):
    with bridge_nad(namespace=namespace, name="mpls", bridge=BRIDGE_BR1) as mpls:
        yield mpls


@pytest.fixture(scope='class')
def all_nads(namespace, dot1q_nad, dhcp_nad, custom_eth_type_llpd_nad, mpls_nad):
    return [dot1q_nad.name, custom_eth_type_llpd_nad.name, dhcp_nad.name, mpls_nad.name]


@pytest.fixture(scope='class')
def bridge_device(network_utility_pods):
    with Bridge(
            name=BRIDGE_BR1, worker_pods=network_utility_pods) as dev:
        yield dev


@pytest.fixture(scope='class')
def vxlan(network_utility_pods, bridge_device, is_bare_metal):

    # There is no need to build vxlan tunnel on bare metal because
    # it has enough physical interfaces for direct connection
    if is_bare_metal or len(network_utility_pods) < 2:
        return

    with VXLANTunnel(
            name="vxlan100",
            worker_pods=network_utility_pods,
            vxlan_id=10,
            master_bridge=bridge_device.name) as vxlan:
        yield vxlan


@pytest.fixture(scope='class')
def vm_a(namespace, all_nads, bridge_device, vxlan):
    dhcp_server_config = (
        "  - sh -c \"echo $'default-lease-time 3600;\\nmax-lease-time 7200;"
        "\\nauthoritative;\\nsubnet 192.168.3.0 netmask 255.255.255.0 {"
        "\\noption subnet-mask 255.255.255.0;\\nrange  "
        f"{VMB_DHCP_ADDRESS} {VMB_DHCP_ADDRESS};"
        "\\n}' > /etc/dhcp/dhcpd.conf\"")  # Inject dhcp configuration to dhcpd.conf

    interface_ip_addresses = ["192.168.0.1", "192.168.2.1", "192.168.3.1", "192.168.4.1", "192.168.1.1"]
    yield from bridge_attached_vm(
        name='vm-fedora-1',
        namespace=namespace.name,
        interfaces=all_nads,
        ip_addresses=interface_ip_addresses,
        cloud_init_script=dhcp_server_config,
        mpls_local_tag=VMA_MPLS_ROUTE_TAG,
        mpls_local_ip=VMA_MPLS_LOOPBACK_IP,
        mpls_dest_ip=VMB_MPLS_LOOPBACK_IP,
        mpls_dest_tag=VMB_MPLS_ROUTE_TAG,
        mpls_route_next_hop="192.168.4.2"
    )


@pytest.fixture(scope='class')
def vm_b(namespace, all_nads, bridge_device, vxlan):
    interface_ip_addresses = ["192.168.0.2", "192.168.2.2", "192.168.3.2", "192.168.4.2", "192.168.1.2"]
    yield from bridge_attached_vm(
        name='vm-fedora-2',
        namespace=namespace.name,
        interfaces=all_nads,
        ip_addresses=interface_ip_addresses,
        mpls_local_tag=VMB_MPLS_ROUTE_TAG,
        mpls_local_ip=VMB_MPLS_LOOPBACK_IP,
        dhcp_pool_address=VMB_DHCP_ADDRESS,
        mpls_dest_ip=VMA_MPLS_LOOPBACK_IP,
        mpls_dest_tag=VMA_MPLS_ROUTE_TAG,
        mpls_route_next_hop="192.168.4.1"
    )


@pytest.fixture(scope='class')
def started_vmi_a(vm_a):
    return running_vmi(vm_a)


@pytest.fixture(scope='class')
def started_vmi_b(vm_b):
    return running_vmi(vm_b)


@pytest.fixture(scope='class')
def configured_vm_a(vm_a, vm_b, started_vmi_a, started_vmi_b):
    """
    Waits until vm_a and vm_b are running and all interfaces are UP then
    runs dhcpd server. To avoid incorrect dhcpd IP address allocation
    this commands are critical to run ONLY after vm_b is UP and configured
    """
    assert utils.wait_for_vm_interfaces(vmi=started_vmi_a, timeout=920)

    assert utils.wait_for_vm_interfaces(
        vmi=started_vmi_b, timeout=920
    )  # This is mandatory step to avoid ip allocation to the incorrect interface
    post_install_command = (["sudo systemctl start dhcpd"])
    run_commands(vm_a.vmi, post_install_command)
    return vm_a


@pytest.fixture(scope='class')
def configured_vm_b(vm_a, vm_b, started_vmi_b, configured_vm_a):
    """
    Starts dhcp client in vm_b
    """
    post_install_command = (
            ["sudo nmcli connection modify eth3 ipv4.method auto", "sudo nmcli con up eth3"])
    run_commands(vm_b.vmi, post_install_command)
    return vm_b
