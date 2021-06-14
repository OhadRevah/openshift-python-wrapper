# -*- coding: utf-8 -*-

"""
Veth interfaces deleted after VMs are removed
"""

import logging

import pytest
from ocp_resources.utils import TimeoutSampler

from utilities.constants import TIMEOUT_3MIN
from utilities.infra import run_ssh_commands
from utilities.network import LINUX_BRIDGE, network_device, network_nad
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


LOGGER = logging.getLogger(__name__)
BR1TEST = "br1test"
BR2TEST = "br2test"

pytestmark = pytest.mark.sno


def count_veth_devices_on_host(worker1_executor, bridge):
    """
    Return how many veth devices exist on the host running pod

    Args:
        worker1_executor (Host): Worker executor.
        bridge (str): Master bridge name.

    Returns:
        int: number of veth devices on host for bridge.
    """
    out = run_ssh_commands(
        host=worker1_executor,
        commands=[
            [
                "bash",
                "-c",
                f"ip -o link show type veth | grep 'master {bridge}' | wc -l",
            ]
        ],
    )[0]
    return int(out.strip())


@pytest.fixture()
def worker1_executor(workers_ssh_executors, worker_node1):
    return workers_ssh_executors[worker_node1.name]


@pytest.fixture()
def remove_veth_br1test_nad(namespace):
    with network_nad(
        nad_type=LINUX_BRIDGE,
        nad_name=BR1TEST,
        interface_name=BR1TEST,
        namespace=namespace,
    ) as nad:
        with network_nad(
            nad_type=LINUX_BRIDGE,
            nad_name=BR2TEST,
            interface_name=BR1TEST,
            namespace=namespace,
        ):
            yield nad


@pytest.fixture()
def remove_veth_bridge_device(
    utility_pods, schedulable_nodes, worker_node1, remove_veth_br1test_nad
):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="veth-removed",
        interface_name=remove_veth_br1test_nad.bridge_name,
        network_utility_pods=utility_pods,
        node_selector=worker_node1.name,
    ) as dev:
        yield dev


@pytest.fixture()
def remove_veth_bridge_attached_vma(namespace, unprivileged_client, worker_node1):
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
        ssh=False,
    ) as vm:
        running_vm(vm=vm, enable_ssh=False, wait_for_interfaces=False)
        yield vm


@pytest.fixture()
def veth_interfaces_exists(worker1_executor, remove_veth_bridge_device):
    assert (
        count_veth_devices_on_host(
            worker1_executor=worker1_executor,
            bridge=remove_veth_bridge_device.bridge_name,
        )
        == 2
    )


@pytest.mark.polarion("CNV-681")
def test_veth_removed_from_host_after_vm_deleted(
    skip_rhel7_workers,
    worker1_executor,
    remove_veth_br1test_nad,
    remove_veth_bridge_device,
    remove_veth_bridge_attached_vma,
    veth_interfaces_exists,
):
    """
    Check that veth interfaces are removed from host after VM deleted
    """
    remove_veth_bridge_attached_vma.delete(wait=True)
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_3MIN,
        sleep=1,
        func=count_veth_devices_on_host,
        worker1_executor=worker1_executor,
        bridge=remove_veth_bridge_device.bridge_name,
    )
    for sample in sampler:
        if sample == 0:
            return True
