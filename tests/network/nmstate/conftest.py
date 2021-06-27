# -*- coding: utf-8 -*-

import logging

import pytest

from tests.network.utils import get_worker_pod, wait_for_address_on_iface
from utilities.infra import get_daemonset_by_name, name_prefix
from utilities.network import LINUX_BRIDGE, network_device
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def node_management_iface_stats_node(nodes_active_nics, worker_node1, worker_node2):
    """
    This function will return a dictionary where  host node name for 2  workers is the
    key and value is another dictionary consist of worker iface_name as key.
    """
    node_stats = {}
    for worker in worker_node1, worker_node2:
        node_stats[worker.name] = {
            "iface_name": nodes_active_nics[worker.name]["occupied"][0]
        }
    return node_stats


@pytest.fixture(scope="module")
def nmstate_vma(schedulable_nodes, worker_node1, namespace, unprivileged_client):
    name = "vma"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=worker_node1.name,
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def nmstate_vmb(schedulable_nodes, worker_node2, namespace, unprivileged_client):
    name = "vmb"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=worker_node2.name,
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def running_nmstate_vma(nmstate_vma):
    return running_vm(vm=nmstate_vma)


@pytest.fixture(scope="module")
def running_nmstate_vmb(nmstate_vmb):
    return running_vm(vm=nmstate_vmb)


@pytest.fixture(scope="module")
def bridges_on_management_ifaces_node1(
    utility_pods,
    node_management_iface_stats_node,
    worker_node1,
):
    """
    This function will return a dictionary where  host node name of worker0 is the  key
    and value is another dictionary consist of worker0 iface_name and worker0 host ip as key.
    """
    # Assuming for now all nodes has the same management interface name
    management_iface = node_management_iface_stats_node[worker_node1.name]["iface_name"]
    worker_pod = get_worker_pod(
        network_utility_pods=utility_pods, worker_node=worker_node1
    )
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"brext-default-net-{name_prefix(worker_node1.name)}",
        interface_name="brext1",
        network_utility_pods=utility_pods,
        node_selector=worker_node1.name,
        nodes=[worker_node1],
        ports=[management_iface],
        ipv4_enable=True,
        ipv4_dhcp=True,
    ) as br_dev:
        # Wait for bridget to get management ip
        wait_for_address_on_iface(worker_pod=worker_pod, iface_name=br_dev.bridge_name)
        yield br_dev
    # Verify Ip is back to the port
    wait_for_address_on_iface(worker_pod=worker_pod, iface_name=management_iface)


@pytest.fixture(scope="module")
def bridges_on_management_ifaces_node2(
    utility_pods,
    node_management_iface_stats_node,
    worker_node2,
):
    # Assuming for now all nodes has the same management interface name
    management_iface = node_management_iface_stats_node[worker_node2.name]["iface_name"]
    worker_pod = get_worker_pod(
        network_utility_pods=utility_pods, worker_node=worker_node2
    )
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"brext-default-net-{name_prefix(worker_node2.name)}",
        interface_name="brext2",
        network_utility_pods=utility_pods,
        node_selector=worker_node2.name,
        nodes=[worker_node2],
        ports=[management_iface],
        ipv4_enable=True,
        ipv4_dhcp=True,
    ) as br_dev:
        # Wait for bridget to get management ip
        wait_for_address_on_iface(worker_pod=worker_pod, iface_name=br_dev.bridge_name)
        yield br_dev

    # Verify Ip is back to the port
    wait_for_address_on_iface(worker_pod=worker_pod, iface_name=management_iface)


@pytest.fixture()
def nmstate_ds(admin_client, hco_namespace):
    return get_daemonset_by_name(
        admin_client=admin_client,
        daemonset_name="nmstate-handler",
        namespace_name=hco_namespace.name,
    )
