# -*- coding: utf-8 -*-
import shlex
from ipaddress import ip_interface

import pytest

from tests.network.utils import DHCP_SERVER_CONF_FILE, update_cloud_init_extra_user_data
from utilities.network import cloud_init_network_data, network_nad
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    running_vm,
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
DHCP_IP_RANGE_START = "10.200.3.3"
DHCP_IP_RANGE_END = "10.200.3.10"
DOT1Q_VLAN_ID = 10


@pytest.fixture(scope="class")
def dot1q_nad(bridge_device_matrix__class__, network_interface, namespace):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="br1test-nad",
        interface_name=network_interface.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def dhcp_nad(bridge_device_matrix__class__, network_interface, namespace):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="dhcp-broadcast",
        interface_name=network_interface.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def custom_eth_type_llpd_nad(
    bridge_device_matrix__class__, network_interface, namespace
):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="custom-eth-type-icmp",
        interface_name=network_interface.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def mpls_nad(bridge_device_matrix__class__, network_interface, namespace):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="mpls",
        interface_name=network_interface.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def l2_bridge_all_nads(
    namespace, dot1q_nad, dhcp_nad, custom_eth_type_llpd_nad, mpls_nad
):
    return [dot1q_nad.name, custom_eth_type_llpd_nad.name, dhcp_nad.name, mpls_nad.name]


def _cloud_init_data(
    vm_name,
    ip_addresses,
    mpls_local_ip,
    mpls_local_tag,
    mpls_dest_ip,
    mpls_dest_tag,
    mpls_route_next_hop,
    cloud_init_extra_user_data,
):
    network_data_data = {
        "ethernets": {
            "eth1": {"addresses": [f"{ip_addresses[0]}/24"]},
            "eth2": {"addresses": [f"{ip_addresses[1]}/24"]},
            "eth4": {"addresses": [f"{ip_addresses[3]}/24"]},
        },
        "vlans": {
            "eth1.10": {
                "addresses": [f"{ip_addresses[4]}/24"],
                "id": 10,
                "link": "eth1",
            }
        },
    }
    # Only DHCP server VM (vm-fedora-1) should have IP on eth3 interface
    if vm_name == "vm-fedora-1":
        network_data_data["ethernets"]["eth3"] = {
            "addresses": [f"{ip_addresses[2]}/24"]
        }

    # DHCP client VM (vm-fedora-2) should be with dhcp=false, will be activated in test 'test_dhcp_broadcast'.
    if vm_name == "vm-fedora-2":
        network_data_data["ethernets"]["eth3"] = {"dhcp4": False}

    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data.update(cloud_init_network_data(data=network_data_data))

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
    cloud_init_data["userData"]["runcmd"] = runcmd

    if cloud_init_extra_user_data:
        update_cloud_init_extra_user_data(
            cloud_init_data=cloud_init_data["userData"],
            cloud_init_extra_user_data=cloud_init_extra_user_data,
        )

    return cloud_init_data


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
        cloud_init_extra_user_data=None,
        client=None,
        cloud_init_data=None,
        node_selector=None,
    ):

        self.mpls_local_tag = mpls_local_tag
        self.ip_addresses = ip_addresses
        self.mpls_local_ip = ip_interface(address=mpls_local_ip).ip
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
            node_selector=node_selector,
        )

    def to_dict(self):
        self.body = fedora_vm_body(name=self.name)
        res = super().to_dict()
        return res

    @property
    def dot1q_ip(self):
        return self.ip_addresses[4]


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
    cloud_init_extra_user_data=None,
    client=None,
    node_selector=None,
):
    cloud_init_data = _cloud_init_data(
        vm_name=name,
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
        mpls_dest_ip=mpls_dest_ip,
        mpls_dest_tag=mpls_dest_tag,
        mpls_route_next_hop=mpls_route_next_hop,
        cloud_init_extra_user_data=cloud_init_extra_user_data,
        client=client,
        cloud_init_data=cloud_init_data,
        node_selector=node_selector,
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture(scope="class")
def l2_bridge_vm_a(namespace, worker_node1, l2_bridge_all_nads, unprivileged_client):
    dhcpd_data = DHCP_SERVER_CONF_FILE.format(
        DHCP_IP_SUBNET="10.200.3",
        DHCP_IP_RANGE_START=DHCP_IP_RANGE_START,
        DHCP_IP_RANGE_END=DHCP_IP_RANGE_END,
    )
    cloud_init_extra_user_data = {
        "runcmd": [
            dhcpd_data,
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
        interfaces=l2_bridge_all_nads,
        ip_addresses=interface_ip_addresses,
        cloud_init_extra_user_data=cloud_init_extra_user_data,
        mpls_local_tag=VMA_MPLS_ROUTE_TAG,
        mpls_local_ip=VMA_MPLS_LOOPBACK_IP,
        mpls_dest_ip=VMB_MPLS_LOOPBACK_IP,
        mpls_dest_tag=VMB_MPLS_ROUTE_TAG,
        mpls_route_next_hop="10.200.4.2",
        client=unprivileged_client,
        node_selector=worker_node1.name,
    )


@pytest.fixture(scope="class")
def l2_bridge_vm_b(namespace, worker_node2, l2_bridge_all_nads, unprivileged_client):
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
        interfaces=l2_bridge_all_nads,
        ip_addresses=interface_ip_addresses,
        mpls_local_tag=VMB_MPLS_ROUTE_TAG,
        mpls_local_ip=VMB_MPLS_LOOPBACK_IP,
        mpls_dest_ip=VMA_MPLS_LOOPBACK_IP,
        mpls_dest_tag=VMA_MPLS_ROUTE_TAG,
        mpls_route_next_hop="10.200.4.1",
        client=unprivileged_client,
        node_selector=worker_node2.name,
    )


@pytest.fixture(scope="class")
def l2_bridge_running_vm_a(l2_bridge_vm_a):
    return running_vm(vm=l2_bridge_vm_a)


@pytest.fixture(scope="class")
def l2_bridge_running_vm_b(l2_bridge_vm_b):
    return running_vm(vm=l2_bridge_vm_b)


@pytest.fixture(scope="class")
def dhcp_client_eth3_nm_connection_name(l2_bridge_running_vm_b):
    """
    Extracts connection name from nmcli command by device name (eth3) from the rrmngmnt host on the dhcp client.

    Returns:
        str: The connection name
    """
    host_nmcli = l2_bridge_running_vm_b.ssh_exec.network.nmcli
    devices = host_nmcli.get_all_devices()
    connections = host_nmcli.get_all_connections()
    relevant_dev = [dev for dev in devices if dev["name"] == "eth3"]
    relevant_con = [
        con for con in connections if con["device"] == relevant_dev[0]["name"]
    ]

    if not relevant_con:
        assert False, "Could not extract connection name by device - No connections."
    return relevant_con[0]["name"]


@pytest.fixture(scope="class")
def configured_l2_bridge_vm_a(
    l2_bridge_vm_a, l2_bridge_vm_b, l2_bridge_running_vm_a, l2_bridge_running_vm_b
):
    l2_bridge_running_vm_a.ssh_exec.run_command(
        command=shlex.split("sudo systemctl start dhcpd")
    )
    return l2_bridge_vm_a
