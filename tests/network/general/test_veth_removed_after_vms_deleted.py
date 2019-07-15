# -*- coding: utf-8 -*-

"""
Veth interfaces deleted after VMs are removed
"""

import logging

import pytest

from resources.namespace import Namespace
import tests.network.utils as net_utils
from tests.utils import FedoraVirtualMachine
from utilities import utils

LOGGER = logging.getLogger(__name__)
BR1TEST = "br1test"
BR1VLAN100 = "br1vlan100"
NETWORKS = {"net1": BR1TEST, "net2": BR1VLAN100}


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
def namespace():
    with Namespace(name=__name__.split(".")[-1].replace("_", "-")) as ns:
        yield ns


@pytest.fixture()
def br1test_nad(namespace):
    with net_utils.bridge_nad(namespace=namespace, name=BR1TEST, bridge=BR1TEST) as nad:
        yield nad


@pytest.fixture()
def br1vlan100_nad(namespace):
    with net_utils.bridge_nad(
        namespace=namespace, name=BR1VLAN100, bridge=BR1TEST
    ) as nad:
        yield nad


@pytest.fixture()
def bridge_device(network_utility_pods):
    with net_utils.Bridge(name=BR1TEST, worker_pods=network_utility_pods) as dev:
        yield dev


@pytest.fixture()
def bridge_attached_vma(namespace):
    with FedoraVirtualMachine(
        namespace=namespace.name,
        name="vma",
        networks=NETWORKS,
        interfaces=sorted(NETWORKS.keys()),
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture()
def bridge_attached_vmb(namespace):
    with FedoraVirtualMachine(
        namespace=namespace.name,
        name="vmb",
        networks=NETWORKS,
        interfaces=sorted(NETWORKS.keys()),
    ) as vm:
        vm.start()
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
    network_utility_pods,
    br1test_nad,
    br1vlan100_nad,
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
                host_veth_before_delete = count_veth_devices_on_host(pod)
                expect_host_veth = host_veth_before_delete - len(vmi_interfaces)
                vm.delete(wait=True)

                sampler = utils.TimeoutSampler(
                    timeout=30, sleep=1, func=count_veth_devices_on_host, pod=pod
                )
                for sample in sampler:
                    if sample == expect_host_veth:
                        return True
