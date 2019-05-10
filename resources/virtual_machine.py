# -*- coding: utf-8 -*-

import logging

from utilities import utils
from .node import Node
from .resource import TIMEOUT, NamespacedResource
from .virtual_machine_instance import VirtualMachineInstance

LOGGER = logging.getLogger(__name__)


def get_base_vmi_spec():
    return {
        "domain": {
            "devices": {
                "disks": [{
                    "disk": {
                        "bus": "virtio",
                    },
                    "name": "containerdisk",
                }],
            },
            "machine": {
                "type": "",
            },
            "resources": {
                "requests": {
                    "memory": "64M",
                },
            },
        },
        "terminationGracePeriodSeconds": 0,
        "volumes": [{
            "name": "containerdisk",
            "containerDisk": {
                "image": "kubevirt/cirros-container-disk-demo:latest",
            },
        }],
    }


class VirtualMachine(NamespacedResource):
    """
    Virtual Machine object, inherited from Resource.
    Implements actions start / stop / status / wait for VM status / is running
    """
    api_version = 'kubevirt.io/v1alpha3'

    def _to_dict(self):
        res = super()._to_dict()
        res["spec"] = {
            "template": {
                "spec": get_base_vmi_spec(),
            },
            "running": False,
        }
        return res

    def start(self, timeout=TIMEOUT, wait=False):
        """
        Start VM with virtctl
        Args:
            timeout (int): Time to wait for the resource.
            wait (bool): If True wait else Not

        Returns:
            True if VM started, else False
        """
        res = utils.run_virtctl_command(
            command=["start", self.name], namespace=self.namespace
        )[0]
        if wait and res:
            return self.wait_for_status(timeout=timeout, status=True)
        return res

    def stop(self, timeout=TIMEOUT, wait=False):
        """
        Stop VM with virtctl
        Args:
            timeout (int): Time to wait for the resource.
            wait (bool): If True wait else Not

        Returns:
            bool: True if VM stopped, else False
        """
        res = utils.run_virtctl_command(
            command=["stop", self.name], namespace=self.namespace
        )[0]
        if wait and res:
            return self.wait_for_status(timeout=timeout, status=False)
        return res

    def wait_for_status(self, status, timeout=TIMEOUT, label_selector=None, resource_version=None):
        """
        Wait for resource to be in status

        Args:
            status (bool): Expected status.
            timeout (int): Time to wait for the resource.
            label_selector (str): The label selector with which to filter results
            resource_version (str): The version with which to filter results. Only events with
                a resource_version greater than this value will be returned

        Returns:
            bool: True if resource in desire status, False if timeout reached.
        """
        LOGGER.info(f"Wait for {self.kind} {self.name} status to be {status}")
        resources = self.api()
        for rsc in resources.watch(
            namespace=self.namespace,
            timeout=timeout,
            label_selector=label_selector,
            resource_version=resource_version
        ):
            if rsc['raw_object']['spec']['running'] == status:
                return True
        return False

    @property
    def node(self):
        """
        Get the node name where the VM is running

        Returns:
            Node: Node
        """
        return Node(name=self.instance.status.nodeName)

    @property
    def vmi(self):
        """
        Get VMI

        Returns:
            VirtualMachineInstance: VMI
        """
        return VirtualMachineInstance(name=self.name, namespace=self.namespace)

    def ready(self):
        """
        Get VM status

        Returns:
            bool: True if Running else False
        """
        LOGGER.info(f"Check if {self.kind} {self.name} is ready")
        return self.instance.status['ready']
