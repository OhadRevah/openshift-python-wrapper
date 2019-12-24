# -*- coding: utf-8 -*-

import logging

import pytest
import tests.network.utils as network_utils
from resources.node_network_state import NodeNetworkState
from resources.utils import TimeoutSampler
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


LOGGER = logging.getLogger(__name__)


def check_address_on_iface(
    network_utility_pods, node_management_iface_stats, dst_iface_name
):
    for pod in network_utility_pods:
        node_network_state = NodeNetworkState(name=pod.node.name)
        for interface in node_network_state.instance.status.currentState.interfaces:
            if interface["name"] == dst_iface_name:
                ip = interface["ipv4"]["address"][0]["ip"]
                if ip != node_management_iface_stats[pod.node.name]["ipv4"]:
                    raise ValueError(
                        f"{dst_iface_name} didn`t get management ip as expected"
                    )
                else:
                    LOGGER.info(
                        f"Node {pod.node.name}: {ip} moved to {dst_iface_name} successfully"
                    )


def wait_for_address_on_iface(
    network_utility_pods, node_management_iface_stats, dst_iface_name
):
    samples = TimeoutSampler(
        timeout=30,
        sleep=1,
        func=check_address_on_iface,
        network_utility_pods=network_utility_pods,
        node_management_iface_stats=node_management_iface_stats,
        dst_iface_name=dst_iface_name,
    )
    # The first time a value is returned means success,
    # In case of an error / timeout an exception will be thrown
    next(iter(samples))


@pytest.fixture(scope="module")
def node_management_iface_stats(network_utility_pods):
    # Create a dictionary of management interface name and management interface ip per node
    management_interfaces = {}
    for pod in network_utility_pods:
        lowest_metric = None
        iface_name = None
        node_network_state = NodeNetworkState(name=pod.node.name)
        for route in node_network_state.instance.status.currentState.routes.running:
            if route["destination"] == "0.0.0.0/0":
                if lowest_metric is None:
                    lowest_metric = route["metric"]
                    iface_name = route["next-hop-interface"]
                elif route["metric"] < lowest_metric:
                    lowest_metric = route["metric"]
                    iface_name = route["next-hop-interface"]
        management_interfaces[pod.node.name] = {"iface_name": iface_name}

        for interface in node_network_state.instance.status.currentState.interfaces:
            if interface["name"] == management_interfaces[pod.node.name]["iface_name"]:
                management_interfaces[pod.node.name]["ipv4"] = interface["ipv4"][
                    "address"
                ][0]["ip"]

    return management_interfaces


@pytest.fixture(scope="module")
def vma(nodes, namespace, unprivileged_client):
    name = "vma"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=nodes[0].name,
        client=unprivileged_client,
        body=fedora_vm_body(name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def vmb(nodes, namespace, unprivileged_client):
    name = "vmb"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=nodes[1].name,
        client=unprivileged_client,
        body=fedora_vm_body(name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def running_vma(vma):
    vma.vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vma.vmi)
    return vma


@pytest.fixture(scope="module")
def running_vmb(vmb):
    vmb.vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmb.vmi)
    return vmb


@pytest.fixture(scope="class")
def bridges_on_management_ifaces(
    network_utility_pods, nodes_active_nics, node_management_iface_stats, nodes
):
    # Assuming for now all nodes has the same management interface name
    management_iface = node_management_iface_stats[network_utility_pods[0].node.name][
        "iface_name"
    ]

    with network_utils.bridge_device(
        bridge_type=network_utils.LINUX_BRIDGE,
        nncp_name="brext-default-net",
        bridge_name="brext",
        network_utility_pods=network_utility_pods,
        nodes=nodes,
        ports=[management_iface],
        ipv4_dhcp=True,
    ) as br_dev:
        # Wait for bridget to get management ip
        wait_for_address_on_iface(
            network_utility_pods, node_management_iface_stats, br_dev.bridge_name
        )
        yield br_dev

    # Verify Ip is back to the port
    wait_for_address_on_iface(
        network_utility_pods, node_management_iface_stats, management_iface
    )
