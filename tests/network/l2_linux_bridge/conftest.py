# -*- coding: utf-8 -*-
from ipaddress import ip_interface

import pytest
from tests.network.utils import linux_bridge_nad, nmcli_add_con_cmds
from tests.utils import (
    Bridge,
    VirtualMachineForTests,
    VXLANTunnel,
    create_ns,
    vm_console_run_commands,
    wait_for_vm_interfaces,
)
from utilities import console


#: Test setup
#       .........                                                                                      ..........
#       |       |---eth1:192.168.0.1:                                              192.168.0.2:---eth1:|        |
#       |       |---eth1.10:192.168.1.1 :dot1q test :                            192.168.1.2:eth1.10---|        |
#       | VM-A  |---eth2:192.168.2.1    : multicast(ICMP), custom eth type test:    192.168.2.2:eth2---|  VM-B  |
#       |       |---eth3:192.168.3.1    : DHCP test :                               192.168.3.2:eth3---|        |
#       |.......|---eth4:192.168.4.1    : mpls test :                               192.168.4.2:eth4---|........|

BRIDGE_BR1 = "br1test"
VMA_MPLS_LOOPBACK_IP = "192.168.100.1/32"
VMA_MPLS_ROUTE_TAG = 100
VMB_MPLS_LOOPBACK_IP = "192.168.200.1/32"
VMB_MPLS_ROUTE_TAG = 200
VMB_DHCP_ADDRESS = "192.168.3.3"
DOT1Q_VLAN_ID = 10


class VirtualMachineAttachedToBridge(VirtualMachineForTests):
    def __init__(
        self,
        name,
        namespace,
        interfaces,
        ip_addresses,
        mpls_local_tag,
        mpls_local_ip,
        mpls_dest_ip,
        mpls_dest_tag,
        mpls_route_next_hop,
        dhcp_pool_address,
        cloud_init_extra_user_data=None,
        client=None,
    ):

        self.mpls_local_tag = mpls_local_tag
        self.ip_addresses = ip_addresses
        self.mpls_local_ip = ip_interface(mpls_local_ip).ip
        self.dhcp_pool_address = dhcp_pool_address
        self.mpls_dest_ip = mpls_dest_ip
        self.mpls_dest_tag = mpls_dest_tag
        self.mpls_route_next_hop = mpls_route_next_hop
        self.cloud_init_extra_user_data = cloud_init_extra_user_data

        networks = {}
        for network in interfaces:
            networks.update({network: network})

        super().__init__(
            name=name,
            namespace=namespace,
            interfaces=interfaces,
            networks=networks,
            client=client,
        )

    def _cloud_init_user_data(self):
        data = super()._cloud_init_user_data()

        bootcmds = []
        bootcmds.extend(nmcli_add_con_cmds("eth1", self.ip_addresses[0]))
        bootcmds.extend(nmcli_add_con_cmds("eth2", self.ip_addresses[1]))
        bootcmds.extend(nmcli_add_con_cmds("eth3", self.ip_addresses[2]))
        bootcmds.extend(nmcli_add_con_cmds("eth4", self.ip_addresses[3]))
        bootcmds.append(
            "nmcli conn add con-name VLAN_10 type vlan ifname eth1.10 ipv4.method manual ipv4.addresses "
            f"{self.ip_addresses[4]}/24 dev eth1 vlan.id {DOT1Q_VLAN_ID} ipv6.method ignore autoconnect true"
        )

        data["bootcmd"] = bootcmds

        runcmd = [
            "modprobe mpls_router",  # In order to test mpls we need to load driver
            "sysctl -w net.mpls.platform_labels=1000",  # Activate mpls labeling feature
            "sysctl -w net.mpls.conf.eth4.input=1",  # Allow incoming mpls traffic
            "sysctl -w net.ipv4.conf.all.arp_ignore=1",  # 2 kernel flags are used to disable wrong arp behavior
            "sysctl -w net.ipv4.conf.all.arp_announce=2",  # Send arp reply only if ip belongs to the interface
            f"ip addr add {self.mpls_local_ip} dev lo",
            f"ip -f mpls route add {self.mpls_local_tag} dev lo",
            "nmcli connection up eth4",  # In order to add mpls route we need to make sure that connection is UP
            f"ip route add {self.mpls_dest_ip} encap mpls {self.mpls_dest_tag} via inet {self.mpls_route_next_hop}",
            "nmcli connection up eth2",
            "ip route add 224.0.0.0/4 dev eth2",
        ]
        data["runcmd"] = runcmd

        if self.cloud_init_extra_user_data:
            for k, v in self.cloud_init_extra_user_data.items():
                data[k] = data[k] + v

        return data

    @property
    def dot1q_ip(self):
        return self.ip_addresses[4]


def running_vmi(vm):
    vm.start(wait=True)
    vm.vmi.wait_until_running()
    return vm.vmi


def bridge_attached_vm(
    name,
    namespace,
    interfaces,
    ip_addresses,
    mpls_local_tag,
    mpls_dest_ip,
    mpls_dest_tag,
    mpls_route_next_hop,
    mpls_local_ip,
    dhcp_pool_address="",
    cloud_init_extra_user_data=None,
    client=None,
):
    with VirtualMachineAttachedToBridge(
        namespace=namespace,
        name=name,
        interfaces=interfaces,
        ip_addresses=ip_addresses,
        mpls_local_tag=mpls_local_tag,
        mpls_local_ip=mpls_local_ip,
        dhcp_pool_address=dhcp_pool_address,
        mpls_dest_ip=mpls_dest_ip,
        mpls_dest_tag=mpls_dest_tag,
        mpls_route_next_hop=mpls_route_next_hop,
        cloud_init_extra_user_data=cloud_init_extra_user_data,
        client=client,
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def namespace(unprivileged_client):
    yield from create_ns(client=unprivileged_client, name="l2-linux-bridge")


@pytest.fixture(scope="class")
def dot1q_nad(namespace):
    with linux_bridge_nad(
        namespace=namespace, name="dot1q", bridge=BRIDGE_BR1
    ) as dot1q_nad:
        yield dot1q_nad


@pytest.fixture(scope="class")
def dhcp_nad(namespace):
    with linux_bridge_nad(
        namespace=namespace, name="dhcp-broadcast", bridge=BRIDGE_BR1
    ) as dhcp_broadcast:
        yield dhcp_broadcast


@pytest.fixture(scope="class")
def custom_eth_type_llpd_nad(namespace):
    with linux_bridge_nad(
        namespace=namespace, name="custom-eth-type-icmp", bridge=BRIDGE_BR1
    ) as custom_eth_type_icmp:
        yield custom_eth_type_icmp


@pytest.fixture(scope="class")
def mpls_nad(namespace):
    with linux_bridge_nad(namespace=namespace, name="mpls", bridge=BRIDGE_BR1) as mpls:
        yield mpls


@pytest.fixture(scope="class")
def all_nads(namespace, dot1q_nad, dhcp_nad, custom_eth_type_llpd_nad, mpls_nad):
    return [dot1q_nad.name, custom_eth_type_llpd_nad.name, dhcp_nad.name, mpls_nad.name]


@pytest.fixture(scope="class")
def bridge_device(network_utility_pods, multi_nics_nodes, nodes_active_nics):
    master_index = 1 if multi_nics_nodes else None

    with Bridge(
        name=BRIDGE_BR1,
        worker_pods=network_utility_pods,
        master_index=master_index,
        nodes_nics=nodes_active_nics,
        disable_vlan_filtering=True,
    ) as br:
        if not multi_nics_nodes:
            with VXLANTunnel(
                name="vxlan100",
                worker_pods=network_utility_pods,
                vxlan_id=10,
                master_bridge=br.name,
                nodes_nics=nodes_active_nics,
            ):
                yield br
        else:
            yield br


@pytest.fixture(scope="class")
def vm_a(namespace, all_nads, bridge_device, unprivileged_client):
    cloud_init_extra_user_data = {
        "runcmd": [
            "sh -c \"echo $'default-lease-time 3600;\\nmax-lease-time 7200;"
            "\\nauthoritative;\\nsubnet 192.168.3.0 netmask 255.255.255.0 {"
            "\\noption subnet-mask 255.255.255.0;\\nrange  "
            f"{VMB_DHCP_ADDRESS} {VMB_DHCP_ADDRESS};"
            "\\n}' > /etc/dhcp/dhcpd.conf\"",  # Inject dhcp configuration to dhcpd.conf
            "sysctl net.ipv4.icmp_echo_ignore_broadcasts=0",  # Enable multicast support
        ]
    }

    interface_ip_addresses = [
        "192.168.0.1",
        "192.168.2.1",
        "192.168.3.1",
        "192.168.4.1",
        "192.168.1.1",
    ]
    yield from bridge_attached_vm(
        name="vm-fedora-1",
        namespace=namespace.name,
        interfaces=all_nads,
        ip_addresses=interface_ip_addresses,
        cloud_init_extra_user_data=cloud_init_extra_user_data,
        mpls_local_tag=VMA_MPLS_ROUTE_TAG,
        mpls_local_ip=VMA_MPLS_LOOPBACK_IP,
        mpls_dest_ip=VMB_MPLS_LOOPBACK_IP,
        mpls_dest_tag=VMB_MPLS_ROUTE_TAG,
        mpls_route_next_hop="192.168.4.2",
        client=unprivileged_client,
    )


@pytest.fixture(scope="class")
def vm_b(namespace, all_nads, bridge_device, unprivileged_client):
    interface_ip_addresses = [
        "192.168.0.2",
        "192.168.2.2",
        "192.168.3.2",
        "192.168.4.2",
        "192.168.1.2",
    ]
    yield from bridge_attached_vm(
        name="vm-fedora-2",
        namespace=namespace.name,
        interfaces=all_nads,
        ip_addresses=interface_ip_addresses,
        mpls_local_tag=VMB_MPLS_ROUTE_TAG,
        mpls_local_ip=VMB_MPLS_LOOPBACK_IP,
        dhcp_pool_address=VMB_DHCP_ADDRESS,
        mpls_dest_ip=VMA_MPLS_LOOPBACK_IP,
        mpls_dest_tag=VMA_MPLS_ROUTE_TAG,
        mpls_route_next_hop="192.168.4.1",
        client=unprivileged_client,
    )


@pytest.fixture(scope="class")
def started_vmi_a(vm_a):
    return running_vmi(vm_a)


@pytest.fixture(scope="class")
def started_vmi_b(vm_b):
    return running_vmi(vm_b)


@pytest.fixture(scope="class")
def configured_vm_a(vm_a, vm_b, started_vmi_a, started_vmi_b):
    """
    Waits until vm_a and vm_b are running and all interfaces are UP then
    runs dhcpd server. To avoid incorrect dhcpd IP address allocation
    this commands are critical to run ONLY after vm_b is UP and configured
    """
    wait_for_vm_interfaces(vmi=started_vmi_a)

    # This is mandatory step to avoid ip allocation to the incorrect interface
    wait_for_vm_interfaces(vmi=started_vmi_b)

    vm_console_run_commands(
        console.Fedora, vm=vm_a, commands=["sudo systemctl start dhcpd"]
    )
    return vm_a


@pytest.fixture(scope="class")
def configured_vm_b(vm_a, vm_b, started_vmi_b, configured_vm_a):
    """
    Starts dhcp client in vm_b
    """
    post_install_command = [
        "sudo nmcli connection modify eth3 ipv4.method auto",
        "sudo nmcli con up eth3",
    ]
    vm_console_run_commands(console.Fedora, vm=vm_b, commands=post_install_command)
    return vm_b
