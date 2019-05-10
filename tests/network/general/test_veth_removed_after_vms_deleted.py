# -*- coding: utf-8 -*-

"""
Veth interfaces deleted after VMs are removed
"""

import contextlib
import logging

import pytest
from pytest_testconfig import config as py_config

from resources.namespace import Namespace
from resources.network_attachment_definition import BridgeNetworkAttachmentDefinition
from resources.virtual_machine import VirtualMachine
from tests.network import utils as net_utils, config
from utilities import utils

LOGGER = logging.getLogger(__name__)
BR1TEST = "br1test"
BR1VLAN100 = "br1vlan100"


def count_veth_devices_on_host(pod, pod_container):
    """
    Return how many veth devices exist on the host running pod

    Args:
        pod (Pod): Pod object.
        pod_container (str): Pod container name.

    Returns:
        int: number of veth devices on host
    """
    out = pod.execute(
        command=['bash', '-c', 'ip -o link show type veth | wc -l'],
        container=pod_container)

    return int(out.strip())


class VirtualMachineAttachedToBridge(VirtualMachine):
    def _add_bridge_interface(self, res, name):
        res['spec']['template']["spec"]["domain"]["devices"]["interfaces"].append({
            "name": name,
            "bridge": {},
        })

    def _add_multus_network(self, res, name, net_name):
        res['spec']['template']["spec"]["networks"].append({
            "name": name,
            "multus": {
                "networkName": net_name,
            },
        })

    def _to_dict(self):
        res = super()._to_dict()
        vm_attrs = {
            "label": "fedora-vm",
            "cpu_cores": 1,
            "memory": "1024Mi",
            "name": self.name
        }
        json_out = utils.generate_yaml_from_template(file_=config.VM_YAML_FEDORA, **vm_attrs)
        res['metadata'] = json_out['metadata']
        res['spec'] = json_out['spec']

        # Add multus networks and interfaces
        net1_network = "net1"
        self._add_multus_network(res=res, name=net1_network, net_name=BR1TEST)
        self._add_bridge_interface(res=res, name=net1_network)

        net2_network = "net2"
        self._add_multus_network(res=res, name=net2_network, net_name=BR1VLAN100)
        self._add_bridge_interface(res=res, name=net2_network)

        return res


@contextlib.contextmanager
def bridge_nad(namespace, name):
    cni_type = py_config['template_defaults']['bridge_cni_name']
    with BridgeNetworkAttachmentDefinition(
            namespace=namespace.name,
            name=name,
            bridge_name=BR1TEST,
            cni_type=cni_type) as nad:
        yield nad


@pytest.fixture()
def namespace():
    with Namespace(name=__name__.split(".")[-1].replace("_", "-")) as ns:
        yield ns


@pytest.fixture()
def br1test_nad(namespace):
    with bridge_nad(namespace=namespace, name=BR1TEST) as nad:
        yield nad


@pytest.fixture()
def br1vlan100_nad(namespace):
    with bridge_nad(namespace=namespace, name=BR1VLAN100) as nad:
        yield nad


@pytest.fixture()
def bridge_device(network_utility_pods):
    with net_utils.Bridge(name=BR1TEST, worker_pods=network_utility_pods) as dev:
        yield from dev


@pytest.fixture()
def bridge_attached_vma(namespace):
    with VirtualMachineAttachedToBridge(namespace=namespace.name, name="vma") as vm:
        assert vm.start()
        yield vm


@pytest.fixture()
def bridge_attached_vmb(namespace):
    with VirtualMachineAttachedToBridge(namespace=namespace.name, name="vmb") as vm:
        assert vm.start()
        yield vm


@pytest.fixture()
def running_bridge_attached_vma(bridge_attached_vma):
    assert bridge_attached_vma.vmi.wait_until_running()
    return bridge_attached_vma


@pytest.fixture()
def running_bridge_attached_vmb(bridge_attached_vmb):
    assert bridge_attached_vmb.vmi.wait_until_running()
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
    running_bridge_attached_vmb
):
    """
    Check that veth interfaces are removed from host after VM deleted
    """
    for vm in (bridge_attached_vma, bridge_attached_vmb):
        vm_interfaces = vm.instance.status.interfaces or []
        for pod in network_utility_pods:
            pod_container = pod.containers()[0].name
            if pod.node.name == vm.node.name:
                host_veth_before_delete = count_veth_devices_on_host(pod, pod_container)
                assert vm.delete(wait=True)
                expect_host_veth = host_veth_before_delete - len(vm_interfaces)

                sampler = utils.TimeoutSampler(
                    timeout=30, sleep=1,
                    func=lambda pod, pod_container, expect_host_veth:
                        count_veth_devices_on_host(pod, pod_container) == expect_host_veth,
                    pod=pod, pod_container=pod_container, expect_host_veth=expect_host_veth
                )
                sampler.wait_for_func_status(result=True)
