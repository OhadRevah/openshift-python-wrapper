# -*- coding: utf-8 -*-

import logging

import pytest
from resources.node_network_configuration_policy import NodeNetworkConfigurationPolicy
from tests.network.host_network.vlan.utils import (
    DHCP_IP_SUBNET,
    dhcp_server_cloud_init_data,
    disable_ipv4_dhcp_client,
    enable_ipv4_dhcp_client,
)
from tests.network.utils import network_device
from utilities import console
from utilities.network import (
    LINUX_BRIDGE,
    BondNodeNetworkConfigurationPolicy,
    VLANInterfaceNodeNetworkConfigurationPolicy,
    get_hosts_common_ports,
    network_nad,
)
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    vm_console_run_commands,
    wait_for_vm_interfaces,
)


LOGGER = logging.getLogger(__name__)


# VLAN on interface fixtures
@pytest.fixture(scope="class")
def vlan_iface_dhcp_client_1(
    network_utility_pods, vlan_base_iface, vlan_tag_id, dhcp_client_1
):
    nncp_name = "dhcp-vlan-client-1-nncp"
    with VLANInterfaceNodeNetworkConfigurationPolicy(
        name=nncp_name,
        worker_pods=network_utility_pods,
        iface_state=NodeNetworkConfigurationPolicy.Interface.State.UP,
        base_iface=vlan_base_iface,
        tag=vlan_tag_id,
        node_selector=dhcp_client_1.name,
        ipv4_dhcp=True,
        ipv6_enable=False,
        teardown=False,
    ) as vlan_iface:
        yield vlan_iface

    vlan_iface = NodeNetworkConfigurationPolicy(name=nncp_name)
    if vlan_iface.exists:
        vlan_iface.clean_up()


@pytest.fixture(scope="class")
def vlan_iface_dhcp_client_2(
    network_utility_pods, vlan_base_iface, vlan_tag_id, dhcp_client_2
):
    nncp_name = "dhcp-vlan-client-2-nncp"
    with VLANInterfaceNodeNetworkConfigurationPolicy(
        name=nncp_name,
        worker_pods=network_utility_pods,
        iface_state=NodeNetworkConfigurationPolicy.Interface.State.UP,
        base_iface=vlan_base_iface,
        tag=vlan_tag_id,
        node_selector=dhcp_client_2.name,
        ipv4_dhcp=True,
        ipv6_enable=False,
        teardown=False,
    ) as vlan_iface:
        yield vlan_iface

    vlan_iface = NodeNetworkConfigurationPolicy(name=nncp_name)
    if vlan_iface.exists:
        vlan_iface.clean_up()


@pytest.fixture(scope="class")
def vlan_iface_on_dhcp_client_2_with_different_tag(
    skip_if_no_multinic_nodes,
    network_utility_pods,
    vlan_base_iface,
    vlan_tag_id,
    dhcp_client_nodes,
    dhcp_client_2,
):
    with VLANInterfaceNodeNetworkConfigurationPolicy(
        worker_pods=network_utility_pods,
        iface_state=NodeNetworkConfigurationPolicy.Interface.State.UP,
        base_iface=vlan_base_iface,
        tag=vlan_tag_id + 1,
        ipv4_dhcp=True,
        ipv6_enable=False,
        node_selector=dhcp_client_2.name,
    ) as vlan_iface:
        yield vlan_iface


@pytest.fixture(scope="module")
def vlan_iface_on_all_nodes(
    skip_if_no_multinic_nodes,
    network_utility_pods,
    nodes_active_nics,
    vlan_tag_id,
    vlan_base_iface,
):
    with VLANInterfaceNodeNetworkConfigurationPolicy(
        worker_pods=network_utility_pods,
        iface_state=NodeNetworkConfigurationPolicy.Interface.State.UP,
        base_iface=vlan_base_iface,
        tag=vlan_tag_id,
    ) as vlan_iface:
        yield vlan_iface


# DHCP VM fixtures
@pytest.fixture(scope="module")
def dhcp_server(running_dhcp_server_vm):
    """
    Once a VM is up and running - start a DHCP server on it.
    """
    vm_console_run_commands(
        console_impl=console.Fedora,
        vm=running_dhcp_server_vm,
        commands=["sudo systemctl start dhcpd"],
    )
    return running_dhcp_server_vm


@pytest.fixture(scope="module")
def dhcp_server_vm(namespace, worker_node1, dhcp_br_nad, unprivileged_client):
    cloud_init_data = dhcp_server_cloud_init_data(
        dhcp_iface_ip_addr=f"{DHCP_IP_SUBNET}.1"
    )
    vm_name = "dhcp-server-vm"

    networks = [dhcp_br_nad.name]
    interfaces = [dhcp_br_nad.bridge_name]

    # At least until https://bugzilla.redhat.com/show_bug.cgi?id=1853028 is fixed -
    # network name in VM spec cannot contain dot.
    vm_interfaces = [iface.replace(".", "-") for iface in interfaces]
    vm_networks = dict(zip(vm_interfaces, networks))

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=vm_name,
        body=fedora_vm_body(vm_name),
        networks=vm_networks,
        interfaces=vm_interfaces,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
        node_selector=worker_node1.name,
    ) as vm:
        yield vm


@pytest.fixture(scope="module")
def running_dhcp_server_vm(dhcp_server_vm):
    dhcp_server_vm.start(wait=True)
    dhcp_server_vm.vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=dhcp_server_vm.vmi)
    return dhcp_server_vm


@pytest.fixture(scope="module")
def dhcp_server_bridge(
    dhcp_server_vlan_iface, network_utility_pods, schedulable_nodes, worker_node1
):
    bridge_name = f"{dhcp_server_vlan_iface.iface_name}-br"
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"{bridge_name}-nncp",
        interface_name=bridge_name,
        network_utility_pods=network_utility_pods,
        nodes=schedulable_nodes,
        ports=[dhcp_server_vlan_iface.iface_name],
        node_selector=worker_node1.name,
    ) as br:
        yield br


@pytest.fixture(scope="module")
def dhcp_br_nad(dhcp_server_bridge, namespace):
    nad_name = f"{dhcp_server_bridge.bridge_name}-nad"

    # Apparently, NetworkAttachmentDefinition name cannot contain dot (although k8s resource naming
    # does allow that - https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#names).
    nad_name = nad_name.replace(".", "-")
    with network_nad(
        namespace=namespace,
        nad_type=LINUX_BRIDGE,
        nad_name=nad_name,
        interface_name=dhcp_server_bridge.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def dhcp_server_vlan_iface(
    skip_if_no_multinic_nodes,
    network_utility_pods,
    worker_node1,
    vlan_base_iface,
    vlan_tag_id,
):
    with VLANInterfaceNodeNetworkConfigurationPolicy(
        name="dhcp-server-vlan-nncp",
        worker_pods=network_utility_pods,
        iface_state=NodeNetworkConfigurationPolicy.Interface.State.UP,
        base_iface=vlan_base_iface,
        tag=vlan_tag_id,
        node_selector=worker_node1.name,
    ) as vlan_iface:
        yield vlan_iface


# DHCP clients fixtures
@pytest.fixture(scope="module")
def dhcp_client_nodes(dhcp_server_vm, network_utility_pods):
    dhcp_client_nodes = []
    for pod in network_utility_pods:
        """
        Allow all nodes to be DHCP clients, except for the one hosting the DHCP server. The reason for this
        exception is a known limitation, where a VLAN DHCP client interface can't be served by a DHCP
        server, if they both run on the same node.
        """
        if pod.node.name != dhcp_server_vm.node_selector:
            dhcp_client_nodes.append(pod.node)
    return dhcp_client_nodes


@pytest.fixture(scope="class")
def dhcp_client_1(dhcp_client_nodes):
    return dhcp_client_nodes[0]


@pytest.fixture(scope="class")
def dhcp_client_2(dhcp_client_nodes):
    return dhcp_client_nodes[1]


@pytest.fixture()
def disabled_dhcp_client_2(vlan_iface_dhcp_client_2, dhcp_client_2):
    disable_ipv4_dhcp_client(
        vlan_iface_nncp=vlan_iface_dhcp_client_2, selected_node=dhcp_client_2.name
    )
    yield dhcp_client_2
    enable_ipv4_dhcp_client(
        vlan_iface_nncp=vlan_iface_dhcp_client_2, selected_node=dhcp_client_2.name
    )


# VLAN on BOND fixtures
@pytest.fixture(scope="class")
def vlan_iface_bond_dhcp_client_1(
    skip_if_no_multinic_nodes,
    network_utility_pods,
    nodes_active_nics,
    dhcp_client_1,
    vlan_tag_id,
):
    with BondNodeNetworkConfigurationPolicy(
        name="bond-dhcp-client-1-nncp",
        bond_name="bond4vlan",
        slaves=get_hosts_common_ports(nodes_active_nics=nodes_active_nics)[1:3],
        worker_pods=network_utility_pods,
        mode="active-backup",
        mtu=1450,
        node_selector=dhcp_client_1.name,
    ) as bond_iface:
        with VLANInterfaceNodeNetworkConfigurationPolicy(
            name="dhcp-vlan-bond-client-1-nncp",
            worker_pods=network_utility_pods,
            iface_state=NodeNetworkConfigurationPolicy.Interface.State.UP,
            base_iface=bond_iface.bond_name,
            tag=vlan_tag_id,
            node_selector=dhcp_client_1.name,
            ipv4_dhcp=True,
            ipv6_enable=False,
        ) as vlan_iface:
            yield vlan_iface


@pytest.fixture(scope="class")
def vlan_iface_bond_dhcp_client_2(
    skip_if_no_multinic_nodes,
    network_utility_pods,
    nodes_active_nics,
    dhcp_client_2,
    vlan_tag_id,
):
    with BondNodeNetworkConfigurationPolicy(
        name="bond-dhcp-client-2-nncp",
        bond_name="bond4vlan",
        slaves=get_hosts_common_ports(nodes_active_nics=nodes_active_nics)[1:3],
        worker_pods=network_utility_pods,
        mode="active-backup",
        mtu=1450,
        node_selector=dhcp_client_2.name,
    ) as bond_iface:
        with VLANInterfaceNodeNetworkConfigurationPolicy(
            name="dhcp-vlan-bond-client-2-nncp",
            worker_pods=network_utility_pods,
            iface_state=NodeNetworkConfigurationPolicy.Interface.State.UP,
            base_iface=bond_iface.bond_name,
            tag=vlan_tag_id,
            node_selector=dhcp_client_2.name,
            ipv4_dhcp=True,
            ipv6_enable=False,
        ) as vlan_iface:
            yield vlan_iface


# General fixtures
@pytest.fixture(scope="module")
def vlan_base_iface(worker_node1, nodes_active_nics):
    # Select the last NIC from the list as a way to ensure that the selected NIC
    # is not already used (e.g. as a bond's slave).
    return nodes_active_nics[worker_node1.name][-1]


@pytest.fixture(scope="module")
def vlan_tag_id(index_number):
    # 1000 is the range start of available VLAN tag IDs.
    return 1000 + next(index_number)
