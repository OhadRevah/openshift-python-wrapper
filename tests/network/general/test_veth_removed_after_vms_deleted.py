# -*- coding: utf-8 -*-

"""
Veth interfaces deleted after VMs are removed
"""

import pytest

from resources.virtual_machine import VirtualMachine
from tests.fixtures import (
    create_vms_from_template,
    wait_until_vmis_running,
    start_vms,
)
from utilities import utils
from . import config


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


@pytest.mark.polarion("CNV-681")
@pytest.mark.usefixtures(
    'network_cr_linux_bridge_br1',
    'network_cr_linux_bridge_br1vlan100',
    'linux_bridge_br1',
    create_vms_from_template.__name__,
    start_vms.__name__,
    wait_until_vmis_running.__name__,
)
class TestVethRemovedAfterVmsDeleted(object):
    """
    Check that veth interfaces are removed from host after VMs deleted
    """
    namespace = config.NETWORK_NS
    vms = config.VETH_REMOVED_VMS
    template = config.VM_YAML_FEDORA
    template_kwargs = config.VM_FEDORA_ATTRS

    def test_veth_removed_from_host_after_vm_deleted(self, network_utility_pods):
        """
        Check that veth interfaces are removed from host after VM deleted
        """
        for vm in self.vms:
            vm_object = VirtualMachine(name=vm, namespace=self.namespace)
            vm_interfaces = vm_object.instance.status.interfaces or []
            for pod in network_utility_pods:
                pod_container = pod.containers()[0].name
                pod_node = pod.node
                if pod_node.name == vm_object.node.name:
                    host_vath_before_delete = count_veth_devices_on_host(pod, pod_container)
                    assert vm_object.delete(wait=True)
                    expect_host_veth = host_vath_before_delete - len(vm_interfaces)

                    sampler = utils.TimeoutSampler(
                        timeout=30, sleep=1,
                        func=lambda pod, pod_container, expect_host_veth:
                            count_veth_devices_on_host(pod, pod_container) == expect_host_veth,
                        pod=pod, pod_container=pod_container, expect_host_veth=expect_host_veth
                    )
                    sampler.wait_for_func_status(result=True)
