# -*- coding: utf-8 -*-

"""
Veth interfaces deleted after VMs are removed
"""
import pytest

from resources.pod import Pod
from resources.virtual_machine import VirtualMachine
from tests.fixtures import (
    create_resources_from_yaml,
    create_vms_from_template,
    wait_for_vms_running,
)
from tests.network.utils import get_host_veth_sampler
from utilities import utils
from . import config
from .fixtures import create_linux_bridge


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
            vm_info = vm_object.get()
            vm_interfaces = vm_info.get('status', {}).get('interfaces', [])
            vm_node = vm_object.node()
            for pod in pytest.privileged_pods:
                pod_object = Pod(name=pod, namespace=pytest.privileged_pods_ns)
                pod_container = pytest.privileged_pod_container
                pod_node = pod_object.node()
                if pod_node == vm_node:
                    err, out = pod_object.exec(
                        command=config.IP_LINK_SHOW_BETH_CMD, container=pod_container
                    )
                    assert err
                    host_vath_before_delete = int(out.strip())
                    assert vm_object.delete(wait=True)
                    expect_host_veth = host_vath_before_delete - len(vm_interfaces)

                    sampler = utils.TimeoutSampler(
                        timeout=30, sleep=1, func=get_host_veth_sampler,
                        pod=pod_object, pod_container=pod_container, expect_host_veth=expect_host_veth
                    )
                    sampler.wait_for_func_status(result=True)
