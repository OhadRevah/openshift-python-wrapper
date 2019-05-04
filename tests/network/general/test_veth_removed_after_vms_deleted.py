# -*- coding: utf-8 -*-

"""
Veth interfaces deleted after VMs are removed
"""

import pytest

from resources.virtual_machine import VirtualMachine
from tests.fixtures import (
    create_resources_from_yaml,
    create_vms_from_template,
    wait_for_vms_running,
)
from utilities import utils
from . import config
from .fixtures import create_linux_bridge


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


@pytest.mark.usefixtures(
    create_resources_from_yaml.__name__,
    create_linux_bridge.__name__,
    create_vms_from_template.__name__,
    wait_for_vms_running.__name__,
)
class TestVethRemovedAfterVmsDeleted(object):
    """
    Check that veth interfaces are removed from host after VMs deleted
    """
    namespace = config.NETWORK_NS
    vms = config.VETH_REMOVED_VMS
    template = config.VM_YAML_TEMPLATE
    bridge_name = config.BRIDGE_BR1
    yamls = [
        config.LINUX_BRIDGE_YAML,
        config.LINUX_BRIDGE_VLAN_100_YAML,
    ]

    def test_veth_removed_from_host_after_vm_deleted(self):
        """
        Check that veth interfaces are removed from host after VM deleted
        """
        for vm in self.vms:
            vm_object = VirtualMachine(name=vm, namespace=self.namespace)
            vm_interfaces = vm_object.instance.status.interfaces or []
            for pod in pytest.privileged_pods:
                pod_container = pod.containers()[0].name
                pod_node = pod.node()
                if pod_node.name == vm_object.node().name:
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
