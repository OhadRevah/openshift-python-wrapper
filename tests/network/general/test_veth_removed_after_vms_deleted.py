# -*- coding: utf-8 -*-

"""
Veth interfaces deleted after VMs are removed
"""

import logging

import pytest
from resources.utils import TimeoutSampler

import tests.network.utils as network_utils
import utilities.network
from utilities.virt import VirtualMachineForTests, fedora_vm_body


LOGGER = logging.getLogger(__name__)
BR1TEST = "br1test"
BR2TEST = "br2test"


def count_veth_devices_on_host(pod, bridge):
    """
    Return how many veth devices exist on the host running pod

    Args:
        pod (Pod): Pod object.
        bridge (str): Master bridge name.

    Returns:
        int: number of veth devices on host for bridge.
    """
    out = pod.execute(
        command=[
            "bash",
            "-c",
            f"ip -o link show type veth | grep 'master {bridge}' | wc -l",
        ]
    )

    return int(out.strip())


@pytest.fixture()
def remove_vath_br1test_nad(namespace):
    with utilities.network.network_nad(
        nad_type=utilities.network.LINUX_BRIDGE,
        nad_name=BR1TEST,
        interface_name=BR1TEST,
        namespace=namespace,
    ) as nad:
        with utilities.network.network_nad(
            nad_type=utilities.network.LINUX_BRIDGE,
            nad_name=BR2TEST,
            interface_name=BR1TEST,
            namespace=namespace,
        ):
            yield nad


@pytest.fixture()
def remove_vath_bridge_device(
    utility_pods, schedulable_nodes, worker_node1, remove_vath_br1test_nad
):
    with network_utils.network_device(
        interface_type=utilities.network.LINUX_BRIDGE,
        nncp_name="veth-removed",
        interface_name=remove_vath_br1test_nad.bridge_name,
        network_utility_pods=utility_pods,
        node_selector=worker_node1.name,
    ) as dev:
        yield dev


@pytest.fixture()
def remove_vath_bridge_attached_vma(namespace, unprivileged_client, worker_node1):
    name = "vma"
    networks = {"net1": BR1TEST, "net2": BR2TEST}
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        networks=networks,
        interfaces=sorted(networks.keys()),
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
        node_selector=worker_node1.name,
        teardown=False,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.fixture()
def worker_pod(utility_pods, worker_node1):
    return network_utils.get_worker_pod(
        network_utility_pods=utility_pods, worker_node=worker_node1
    )


@pytest.fixture()
def veth_interfaces_exists(
    utility_pods, worker_node1, worker_pod, remove_vath_bridge_device
):
    assert (
        count_veth_devices_on_host(
            pod=worker_pod, bridge=remove_vath_bridge_device.bridge_name
        )
        == 2
    )


@pytest.mark.polarion("CNV-681")
def test_veth_removed_from_host_after_vm_deleted(
    skip_rhel7_workers,
    worker_node1,
    utility_pods,
    worker_pod,
    remove_vath_br1test_nad,
    remove_vath_bridge_device,
    remove_vath_bridge_attached_vma,
    veth_interfaces_exists,
):
    """
    Check that veth interfaces are removed from host after VM deleted
    """
    remove_vath_bridge_attached_vma.delete(wait=True)
    sampler = TimeoutSampler(
        timeout=180,
        sleep=1,
        func=count_veth_devices_on_host,
        pod=worker_pod,
        bridge=remove_vath_bridge_device.bridge_name,
    )
    for sample in sampler:
        if sample == 0:
            return True
