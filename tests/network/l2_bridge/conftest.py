# -*- coding: utf-8 -*-
import shlex
from ipaddress import ip_interface

import pytest
from ocp_resources.node_network_state import NodeNetworkState
from ocp_resources.resource import ResourceEditor

from tests.network.constants import DHCP_IP_RANGE_END, DHCP_IP_RANGE_START
from tests.network.utils import (
    DHCP_SERVER_CONF_FILE,
    DHCP_SERVICE_RESTART,
    update_cloud_init_extra_user_data,
)
from utilities.infra import name_prefix, run_ssh_commands
from utilities.network import cloud_init_network_data, network_device, network_nad
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    prepare_cloud_init_user_data,
    running_vm,
)


#: Test setup
#       .........                                                                                      ..........
#       |       |---eth1:10.200.0.1:                                              10.200.0.2:---eth1:|        |
#       | VM-A  |---eth2:10.200.2.1    : multicast(ICMP), custom eth type test:    10.200.2.2:eth2---|  VM-B  |
#       |       |---eth3:10.200.3.1    : DHCP test :                               10.200.3.2:eth3---|        |
#       |.......|---eth4:10.200.4.1    : mpls test :                               10.200.4.2:eth4---|........|

VMA_MPLS_LOOPBACK_IP = "10.200.100.1/32"
VMA_MPLS_ROUTE_TAG = 100
VMB_MPLS_LOOPBACK_IP = "10.200.200.1/32"
VMB_MPLS_ROUTE_TAG = 200


@pytest.fixture(scope="class")
def l2_bridge_device_name(index_number):
    yield f"br{next(index_number)}test"


@pytest.fixture(scope="class")
def l2_bridge_device_worker_1(
    bridge_device_matrix__class__,
    nodes_available_nics,
    utility_pods,
    worker_node1,
    l2_bridge_device_name,
):
    with network_device(
        interface_type=bridge_device_matrix__class__,
        nncp_name=f"l2-bridge-{name_prefix(worker_node1.name)}",
        interface_name=l2_bridge_device_name,
        network_utility_pods=utility_pods,
        node_selector=worker_node1.name,
        ports=[nodes_available_nics[worker_node1.name][0]],
    ) as br:
        yield br


@pytest.fixture(scope="class")
def l2_bridge_device_worker_2(
    bridge_device_matrix__class__,
    nodes_available_nics,
    utility_pods,
    worker_node2,
    l2_bridge_device_name,
):
    with network_device(
        interface_type=bridge_device_matrix__class__,
        nncp_name=f"l2-bridge-{name_prefix(worker_node2.name)}",
        interface_name=l2_bridge_device_name,
        network_utility_pods=utility_pods,
        node_selector=worker_node2.name,
        ports=[nodes_available_nics[worker_node2.name][0]],
    ) as br:
        yield br


@pytest.fixture(scope="class")
def dhcp_nad(
    bridge_device_matrix__class__,
    namespace,
    l2_bridge_device_worker_1,
    l2_bridge_device_worker_2,
    l2_bridge_device_name,
):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name=f"{l2_bridge_device_name}-dhcp-broadcast-nad",
        interface_name=l2_bridge_device_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def custom_eth_type_llpd_nad(
    bridge_device_matrix__class__,
    namespace,
    l2_bridge_device_worker_1,
    l2_bridge_device_worker_2,
    l2_bridge_device_name,
):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name=f"{l2_bridge_device_name}-custom-eth-type-icmp-nad",
        interface_name=l2_bridge_device_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def mpls_nad(
    bridge_device_matrix__class__,
    namespace,
    l2_bridge_device_worker_1,
    l2_bridge_device_worker_2,
    l2_bridge_device_name,
):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name=f"{l2_bridge_device_name}-mpls-nad",
        interface_name=l2_bridge_device_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def l2_bridge_all_nads(namespace, dhcp_nad, custom_eth_type_llpd_nad, mpls_nad):
    return [custom_eth_type_llpd_nad.name, mpls_nad.name, dhcp_nad.name]


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
    }
    # Only DHCP server VM (vm-fedora-1) should have IP on eth3 interface
    if vm_name == "vm-fedora-1":
        network_data_data["ethernets"]["eth3"] = {
            "addresses": [f"{ip_addresses[2]}/24"]
        }

    # DHCP client VM (vm-fedora-2) should be with dhcp=false, will be activated in test 'test_dhcp_broadcast'.
    if vm_name == "vm-fedora-2":
        network_data_data["ethernets"]["eth3"] = {"dhcp4": False}

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

    cloud_init_data = prepare_cloud_init_user_data(section="runcmd", data=runcmd)
    cloud_init_data.update(cloud_init_network_data(data=network_data_data))

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
    run_ssh_commands(
        host=l2_bridge_running_vm_a.ssh_exec,
        commands=[shlex.split(DHCP_SERVICE_RESTART)],
    )
    return l2_bridge_vm_a


@pytest.fixture()
def started_vmb_dhcp_client(
    l2_bridge_running_vm_b, dhcp_client_eth3_nm_connection_name
):
    nmcli_cmd = "sudo nmcli connection"
    # Start dhcp client in l2_bridge_running_vm_b
    run_ssh_commands(
        host=l2_bridge_running_vm_b.ssh_exec,
        commands=[
            shlex.split(
                f"{nmcli_cmd} modify '{dhcp_client_eth3_nm_connection_name}' ipv4.method auto"
            ),
            shlex.split(f"{nmcli_cmd} up '{dhcp_client_eth3_nm_connection_name}'"),
            shlex.split("sudo systemctl restart qemu-guest-agent.service"),
        ],
    )


@pytest.fixture()
def modified_nncp(configured_l2_bridge_vm_a, l2_bridge_device_worker_1):
    # Get the current MTU of the bridge. It can be taken from any NodeNetworkState, but get it specifically from
    # the VMI's hosting node, to make sure the NNCP includes an actual diff from the current state where the VMI runs.
    nns = NodeNetworkState(name=configured_l2_bridge_vm_a.vmi.node.name)
    bridge_mtu = [
        br
        for br in nns.interfaces
        if br["name"] == l2_bridge_device_worker_1.bridge_name
    ][0]["mtu"]

    l2_bridge_device_worker_1.iface.update({"mtu": bridge_mtu - 100})
    ResourceEditor(
        patches={
            l2_bridge_device_worker_1: {
                "spec": {
                    "desiredState": {
                        "interfaces": l2_bridge_device_worker_1.iface,
                    },
                },
            },
        }
    ).update(backup_resources=True)


@pytest.fixture()
def restarted_vms(configured_l2_bridge_vm_a, l2_bridge_running_vm_b):
    for vm in (configured_l2_bridge_vm_a, l2_bridge_running_vm_b):
        vm.stop(wait=True)
        running_vm(vm=vm, enable_ssh=False)
