# -*- coding: utf-8 -*-
from ipaddress import ip_interface

import pytest
from tests.network.utils import nmcli_add_con_cmds, update_cloud_init_extra_user_data
from utilities import console
from utilities.network import bridge_nad
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    vm_console_run_commands,
    wait_for_vm_interfaces,
)


#: Test setup
#       .........                                                                                      ..........
#       |       |---eth1:10.200.0.1:                                              10.200.0.2:---eth1:|        |
#       |       |---eth1.10:10.200.1.1 :dot1q test :                            10.200.1.2:eth1.10---|        |
#       | VM-A  |---eth2:10.200.2.1    : multicast(ICMP), custom eth type test:    10.200.2.2:eth2---|  VM-B  |
#       |       |---eth3:10.200.3.1    : DHCP test :                               10.200.3.2:eth3---|        |
#       |.......|---eth4:10.200.4.1    : mpls test :                               10.200.4.2:eth4---|........|

VMA_MPLS_LOOPBACK_IP = "10.200.100.1/32"
VMA_MPLS_ROUTE_TAG = 100
VMB_MPLS_LOOPBACK_IP = "10.200.200.1/32"
VMB_MPLS_ROUTE_TAG = 200
VMB_DHCP_ADDRESS = "10.200.3.3"
DOT1Q_VLAN_ID = 10


@pytest.fixture(scope="class")
def dot1q_nad(bridge_device_matrix__class__, ovs_lb_bridge, namespace):
    with bridge_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="br1test-nad",
        bridge_name=ovs_lb_bridge.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def dhcp_nad(bridge_device_matrix__class__, ovs_lb_bridge, namespace):
    with bridge_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="dhcp-broadcast",
        bridge_name=ovs_lb_bridge.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def custom_eth_type_llpd_nad(bridge_device_matrix__class__, ovs_lb_bridge, namespace):
    with bridge_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="custom-eth-type-icmp",
        bridge_name=ovs_lb_bridge.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def mpls_nad(bridge_device_matrix__class__, ovs_lb_bridge, namespace):
    with bridge_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="mpls",
        bridge_name=ovs_lb_bridge.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def all_nads(namespace, dot1q_nad, dhcp_nad, custom_eth_type_llpd_nad, mpls_nad):
    return [dot1q_nad.name, custom_eth_type_llpd_nad.name, dhcp_nad.name, mpls_nad.name]


def _cloud_init_data(
    ip_addresses,
    mpls_local_ip,
    mpls_local_tag,
    mpls_dest_ip,
    mpls_dest_tag,
    mpls_route_next_hop,
    cloud_init_extra_user_data,
):
    data = FEDORA_CLOUD_INIT_PASSWORD

    bootcmds = []
    bootcmds.extend(nmcli_add_con_cmds("eth1", ip_addresses[0]))
    bootcmds.extend(nmcli_add_con_cmds("eth2", ip_addresses[1]))
    bootcmds.extend(nmcli_add_con_cmds("eth3", ip_addresses[2]))
    bootcmds.extend(nmcli_add_con_cmds("eth4", ip_addresses[3]))
    bootcmds.append(
        "nmcli conn add con-name VLAN_10 type vlan ifname eth1.10 ipv4.method manual ipv4.addresses "
        f"{ip_addresses[4]}/24 dev eth1 vlan.id {DOT1Q_VLAN_ID} ipv6.method ignore autoconnect true"
    )

    data["bootcmd"] = bootcmds

    runcmd = [
        "modprobe mpls_router",  # In order to test mpls we need to load driver
        "sysctl -w net.mpls.platform_labels=1000",  # Activate mpls labeling feature
        "sysctl -w net.mpls.conf.eth4.input=1",  # Allow incoming mpls traffic
        "sysctl -w net.ipv4.conf.all.arp_ignore=1",  # 2 kernel flags are used to disable wrong arp behavior
        "sysctl -w net.ipv4.conf.all.arp_announce=2",  # Send arp reply only if ip belongs to the interface
        f"ip addr add {mpls_local_ip} dev lo",
        f"ip -f mpls route add {mpls_local_tag} dev lo",
        "nmcli connection up eth4",  # In order to add mpls route we need to make sure that connection is UP
        f"ip route add {mpls_dest_ip} encap mpls {mpls_dest_tag} via inet {mpls_route_next_hop}",
        "nmcli connection up eth2",
        "ip route add 224.0.0.0/4 dev eth2",
    ]
    data["runcmd"] = runcmd

    if cloud_init_extra_user_data:
        update_cloud_init_extra_user_data(
            cloud_init_data=data, cloud_init_extra_user_data=cloud_init_extra_user_data
        )
    return data


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
        cloud_init_data=None,
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
            cloud_init_data=cloud_init_data,
        )

    def to_dict(self):
        self.body = fedora_vm_body(self.name)
        res = super().to_dict()
        return res

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
    cloud_init_data = _cloud_init_data(
        ip_addresses=ip_addresses,
        mpls_local_ip=mpls_local_ip,
        mpls_local_tag=mpls_local_tag,
        mpls_dest_ip=mpls_dest_ip,
        mpls_dest_tag=mpls_dest_tag,
        mpls_route_next_hop=mpls_route_next_hop,
        cloud_init_extra_user_data=cloud_init_extra_user_data,
    )
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
        cloud_init_data=cloud_init_data,
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def vm_a(namespace, all_nads, unprivileged_client):
    cloud_init_extra_user_data = {
        "runcmd": [
            "sh -c \"echo $'default-lease-time 3600;\\nmax-lease-time 7200;"
            "\\nauthoritative;\\nsubnet 10.200.3.0 netmask 255.255.255.0 {"
            "\\noption subnet-mask 255.255.255.0;\\nrange  "
            f"{VMB_DHCP_ADDRESS} {VMB_DHCP_ADDRESS};"
            "\\n}' > /etc/dhcp/dhcpd.conf\"",  # Inject dhcp configuration to dhcpd.conf
            "sysctl net.ipv4.icmp_echo_ignore_broadcasts=0",  # Enable multicast support
        ]
    }

    interface_ip_addresses = [
        "10.200.0.1",
        "10.200.2.1",
        "10.200.3.1",
        "10.200.4.1",
        "10.200.1.1",
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
        mpls_route_next_hop="10.200.4.2",
        client=unprivileged_client,
    )


@pytest.fixture(scope="class")
def vm_b(namespace, all_nads, unprivileged_client):
    interface_ip_addresses = [
        "10.200.0.2",
        "10.200.2.2",
        "10.200.3.2",
        "10.200.4.2",
        "10.200.1.2",
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
        mpls_route_next_hop="10.200.4.1",
        client=unprivileged_client,
    )


@pytest.fixture(scope="class")
def started_vmi_a(vm_a):
    return running_vmi(vm=vm_a)


@pytest.fixture(scope="class")
def started_vmi_b(vm_b):
    return running_vmi(vm=vm_b)


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
