# -*- coding: utf-8 -*-

import logging

import pytest
from resources.node_network_configuration_policy import NodeNetworkConfigurationPolicy
from tests.network.utils import (
    bridge_device,
    bridge_nad,
    nmcli_add_con_cmds,
    update_cloud_init_extra_user_data,
)
from utilities import console
from utilities.network import (
    BondNodeNetworkConfigurationPolicy,
    VLANInterfaceNodeNetworkConfigurationPolicy,
)
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    vm_console_run_commands,
    wait_for_vm_interfaces,
)


LOGGER = logging.getLogger(__name__)

DHCP_IP_SUBNET = "192.168.1"
DHCP_IP_RANGE_START = f"{DHCP_IP_SUBNET}.3"
DHCP_IP_RANGE_END = f"{DHCP_IP_SUBNET}.100"


@pytest.fixture(scope="module")
def vlan_iface_on_all_nodes(
    skip_if_no_multinic_nodes, network_utility_pods, nodes_active_nics, vlan_tag_id,
):
    # Select the last NIC from the list as a way to ensure that the selected NIC is not already used (e.g. as
    # a bond's slave).
    vlan_base_iface = nodes_active_nics[network_utility_pods[0].node.name][-1]

    with VLANInterfaceNodeNetworkConfigurationPolicy(
        worker_pods=network_utility_pods,
        iface_state=NodeNetworkConfigurationPolicy.Interface.State.UP,
        base_iface=vlan_base_iface,
        tag=vlan_tag_id,
        teardown=False,
    ) as vlan_iface:
        yield vlan_iface


@pytest.fixture(scope="module")
def vlan_iface_on_one_node_with_different_tag(
    skip_if_no_multinic_nodes,
    network_utility_pods,
    vlan_iface_on_all_nodes,
    dhcp_server,
):
    vlan_base_iface = vlan_iface_on_all_nodes.base_iface
    iface_tag = vlan_iface_on_all_nodes.tag + 1

    for pod in network_utility_pods:
        if pod.node.name != dhcp_server.node_selector:
            node_selector = pod.node.name
            break

    with VLANInterfaceNodeNetworkConfigurationPolicy(
        worker_pods=network_utility_pods,
        iface_state=NodeNetworkConfigurationPolicy.Interface.State.UP,
        base_iface=vlan_base_iface,
        tag=iface_tag,
        ipv4_dhcp=True,
        ipv6_enable=False,
        node_selector=node_selector,
    ) as vlan_iface:
        yield vlan_iface


@pytest.fixture(scope="module")
def dhcp_server(running_dhcp_server_vm):
    """
    Once a VM is up and running - start a DHCP server on it.
    """
    vm_console_run_commands(
        console.Fedora,
        vm=running_dhcp_server_vm,
        commands=["sudo systemctl start dhcpd"],
    )
    return running_dhcp_server_vm


@pytest.fixture(scope="module")
def dhcp_server_vm(namespace, node_selector_name, dhcp_br_nad, unprivileged_client):
    cloud_init_data = _dhcp_server_cloud_init_data(
        dhcp_iface_ip_addr=f"{DHCP_IP_SUBNET}.1"
    )
    vm_name = "dhcp-server-vm"

    networks = [dhcp_br_nad.name]
    interfaces = [dhcp_br_nad.bridge_name]
    vm_networks = dict(zip(interfaces, networks))

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=vm_name,
        body=fedora_vm_body(vm_name),
        networks=vm_networks,
        interfaces=interfaces,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
        node_selector=node_selector_name,
    ) as vm:
        yield vm


@pytest.fixture(scope="module")
def running_dhcp_server_vm(dhcp_server_vm):
    dhcp_server_vm.start(wait=True)
    dhcp_server_vm.vmi.wait_until_running()
    wait_for_vm_interfaces(dhcp_server_vm.vmi)
    return dhcp_server_vm


@pytest.fixture(scope="module")
def dhcp_server_bridge(
    vlan_iface_on_all_nodes,
    network_utility_pods,
    schedulable_nodes,
    node_selector_name,
    bridge_device_matrix__module__,
):
    bridge_name = f"{vlan_iface_on_all_nodes.iface_name}-br"
    with bridge_device(
        bridge_type=bridge_device_matrix__module__,
        nncp_name=f"{bridge_name}-nncp",
        bridge_name=bridge_name,
        network_utility_pods=network_utility_pods,
        nodes=schedulable_nodes,
        ports=[vlan_iface_on_all_nodes.iface_name],
        node_selector=node_selector_name,
    ) as br:
        yield br


@pytest.fixture(scope="module")
def dhcp_br_nad(dhcp_server_bridge, namespace, bridge_device_matrix__module__):
    nad_name = f"{dhcp_server_bridge.bridge_name}-nad"

    # Apparently, NetworkAttachmentDefinition name cannot contain dot (although k8s resource naming
    # does allow that - https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#names).
    nad_name = nad_name.replace(".", "-")
    with bridge_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__module__,
        nad_name=nad_name,
        bridge_name=dhcp_server_bridge.bridge_name,
    ) as nad:
        yield nad


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


@pytest.fixture(scope="module")
def dhcp_client(vlan_iface_on_all_nodes, dhcp_client_nodes):
    for node in dhcp_client_nodes:
        enable_ipv4_dhcp_client(
            vlan_iface_nncp=vlan_iface_on_all_nodes, selected_node=node.name
        )


@pytest.fixture(scope="module")
def dhcp_client_on_one_node(selected_dhcp_client, vlan_iface_on_all_nodes):
    enable_ipv4_dhcp_client(
        vlan_iface_nncp=vlan_iface_on_all_nodes, selected_node=selected_dhcp_client.name
    )
    return selected_dhcp_client


@pytest.fixture(scope="module")
def dhcp_client_over_bond(vlan_iface_over_bond_on_all_nodes, dhcp_client_nodes):
    for node in dhcp_client_nodes:
        enable_ipv4_dhcp_client(
            vlan_iface_nncp=vlan_iface_over_bond_on_all_nodes, selected_node=node.name
        )
        vlan_iface_over_bond_on_all_nodes.wait_for_condition(
            condition=vlan_iface_over_bond_on_all_nodes.Conditions.Type.AVAILABLE,
            status="True",
            timeout=60,
        )


@pytest.fixture(scope="module")
def vlan_iface_over_bond_on_all_nodes(
    skip_if_no_multinic_nodes,
    network_utility_pods,
    nodes_active_nics,
    vlan_iface_on_all_nodes,
):
    with BondNodeNetworkConfigurationPolicy(
        name="bond1-nncp",
        bond_name="bond4vlan",
        nodes=[net_pod.node.name for net_pod in network_utility_pods],
        nics=nodes_active_nics[network_utility_pods[0].node.name][2:4],
        worker_pods=network_utility_pods,
        mode="active-backup",
        mtu=1450,
    ) as bond_iface:

        vlan_base_iface = bond_iface.bond_name
        tag_id = vlan_iface_on_all_nodes.tag

        with VLANInterfaceNodeNetworkConfigurationPolicy(
            worker_pods=network_utility_pods,
            iface_state=NodeNetworkConfigurationPolicy.Interface.State.UP,
            base_iface=vlan_base_iface,
            tag=tag_id,
        ) as vlan_iface:
            yield vlan_iface


@pytest.fixture(scope="module")
def selected_dhcp_client(dhcp_client_nodes):
    return dhcp_client_nodes[0]


@pytest.fixture(scope="module")
def node_selector_name(network_utility_pods):
    return network_utility_pods[0].node.name


@pytest.fixture(scope="session")
def vlan_tag_id(index_number):
    # 1000 is the range start of available VLAN tag IDs.
    return 1000 + next(index_number)


@pytest.fixture(scope="function")
def disable_vlan_ipv4_dhcp(vlan_iface_on_all_nodes, dhcp_client_nodes):
    """
    A teardown fixture.
    """
    yield

    for node in dhcp_client_nodes:
        disable_ipv4_dhcp_client(
            vlan_iface_nncp=vlan_iface_on_all_nodes, selected_node=node.name
        )
        vlan_iface_on_all_nodes.wait_for_condition(
            condition=vlan_iface_on_all_nodes.Conditions.Type.AVAILABLE,
            status="True",
            timeout=60,
        )


@pytest.fixture(scope="function")
def remove_node_selector(vlan_iface_on_all_nodes):
    """
    A teardown fixture.
    """
    yield

    resource_dict = {
        "metadata": {"name": vlan_iface_on_all_nodes.name},
        "spec": {"nodeSelector": {"kubernetes.io/hostname": None}},
    }
    vlan_iface_on_all_nodes.update(resource_dict=resource_dict)


def _dhcp_server_cloud_init_data(dhcp_iface_ip_addr):
    cloud_init_extra_user_data = {
        "runcmd": [
            "sh -c \"echo $'default-lease-time 3600;\\nmax-lease-time 7200;"
            f"\\nauthoritative;\\nsubnet {DHCP_IP_SUBNET}.0 netmask 255.255.255.0 "
            "{\\noption subnet-mask 255.255.255.0;\\nrange  "
            f"{DHCP_IP_RANGE_START} {DHCP_IP_RANGE_END};"
            "\\n}' > /etc/dhcp/dhcpd.conf\""
        ]
    }

    data = FEDORA_CLOUD_INIT_PASSWORD

    bootcmds = nmcli_add_con_cmds("eth1", dhcp_iface_ip_addr)
    data["bootcmd"] = bootcmds

    update_cloud_init_extra_user_data(
        cloud_init_data=data, cloud_init_extra_user_data=cloud_init_extra_user_data
    )
    return data


def set_ipv4_dhcp_client(vlan_iface_nncp, enabled, selected_node=None):
    for iface_idx, interface in enumerate(vlan_iface_nncp.desired_state["interfaces"]):
        if interface["type"] == "vlan":
            vlan_iface = vlan_iface_nncp.desired_state["interfaces"].pop(iface_idx)
            vlan_iface.update(
                {
                    "ipv4": {"dhcp": enabled, "enabled": enabled},
                    "ipv6": {"enabled": False},
                }
            )
            vlan_iface_nncp.desired_state["interfaces"].insert(iface_idx, vlan_iface)

            resource_dict = {
                "metadata": {"name": vlan_iface_nncp.name},
                "spec": {
                    "desiredState": {
                        "interfaces": vlan_iface_nncp.desired_state["interfaces"]
                    }
                },
            }
            if selected_node:
                resource_dict["spec"]["nodeSelector"] = {
                    "kubernetes.io/hostname": selected_node
                }

            vlan_iface_nncp.update(resource_dict=resource_dict)


def enable_ipv4_dhcp_client(vlan_iface_nncp, selected_node=None):
    set_ipv4_dhcp_client(vlan_iface_nncp, enabled=True, selected_node=selected_node)


def disable_ipv4_dhcp_client(vlan_iface_nncp, selected_node=None):
    set_ipv4_dhcp_client(vlan_iface_nncp, enabled=False, selected_node=selected_node)
