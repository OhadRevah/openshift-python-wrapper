# -*- coding: utf-8 -*-

"""
Veth interfaces deleted after VMs are removed
"""

import logging

import pytest
import tests.network.utils as network_utils
import utilities.network
from resources.utils import TimeoutSampler
from utilities.virt import VirtualMachineForTests, fedora_vm_body


LOGGER = logging.getLogger(__name__)
BR1TEST = "br1test"
BR2TEST = "br2test"
NETWORKS = {"net1": BR1TEST, "net2": BR2TEST}


def count_veth_devices_on_host(pod):
    """
    Return how many veth devices exist on the host running pod

    Args:
        pod (Pod): Pod object.

    Returns:
        int: number of veth devices on host
    """
    out = pod.execute(command=["bash", "-c", "ip -o link show type veth | wc -l"])

    return int(out.strip())


@pytest.fixture()
def br1test_nad(namespace):
    with utilities.network.bridge_nad(
        nad_type=utilities.network.LINUX_BRIDGE,
        nad_name=BR1TEST,
        bridge_name=BR1TEST,
        namespace=namespace,
    ) as nad:
        yield nad


@pytest.fixture()
def br2test_nad(namespace):
    with utilities.network.bridge_nad(
        nad_type=utilities.network.LINUX_BRIDGE,
        nad_name=BR2TEST,
        bridge_name=BR1TEST,
        namespace=namespace,
    ) as nad:
        yield nad


@pytest.fixture()
def bridge_device(network_utility_pods, schedulable_nodes):
    with network_utils.bridge_device(
        bridge_type=utilities.network.LINUX_BRIDGE,
        nncp_name="veth-removed",
        bridge_name=BR1TEST,
        network_utility_pods=network_utility_pods,
        nodes=schedulable_nodes,
    ) as dev:
        yield dev


@pytest.fixture()
def bridge_attached_vma(namespace, unprivileged_client):
    name = "vma"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        networks=NETWORKS,
        interfaces=sorted(NETWORKS.keys()),
        client=unprivileged_client,
        body=fedora_vm_body(name),
        teardown=False,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.fixture()
def bridge_attached_vmb(namespace, unprivileged_client):
    name = "vmb"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        networks=NETWORKS,
        interfaces=sorted(NETWORKS.keys()),
        client=unprivileged_client,
        body=fedora_vm_body(name),
        teardown=False,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.fixture()
def running_bridge_attached_vma(bridge_attached_vma):
    bridge_attached_vma.vmi.wait_until_running()
    return bridge_attached_vma


@pytest.fixture()
def running_bridge_attached_vmb(bridge_attached_vmb):
    bridge_attached_vmb.vmi.wait_until_running()
    return bridge_attached_vmb


@pytest.mark.polarion("CNV-681")
def test_veth_removed_from_host_after_vm_deleted(
    skip_rhel7_workers,
    network_utility_pods,
    br1test_nad,
    br2test_nad,
    bridge_device,
    bridge_attached_vma,
    bridge_attached_vmb,
    running_bridge_attached_vma,
    running_bridge_attached_vmb,
):
    """
    Check that veth interfaces are removed from host after VM deleted
    """
    for vm in (bridge_attached_vma, bridge_attached_vmb):
        vmi_interfaces = vm.vmi.instance.status.interfaces or []
        for pod in network_utility_pods:
            if pod.node.name == vm.vmi.node.name:
                _delete_vm_and_compare_veth(
                    pod=pod, vm=vm, vmi_interfaces=vmi_interfaces
                )
                break


def _delete_vm_and_compare_veth(pod, vm, vmi_interfaces):
    host_veth_before_delete = count_veth_devices_on_host(pod)
    expect_host_veth = host_veth_before_delete - len(vmi_interfaces)
    vm.delete(wait=True)

    sampler = TimeoutSampler(
        timeout=120, sleep=1, func=count_veth_devices_on_host, pod=pod
    )
    for sample in sampler:
        if sample == expect_host_veth:
            return True
