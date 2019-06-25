# -*- coding: utf-8 -*-

import logging

from utilities import utils
from .node import Node
from .pod import Pod
from .resource import TIMEOUT, NamespacedResource

LOGGER = logging.getLogger(__name__)
API_VERSION = 'kubevirt.io/v1alpha3'


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
    api_version = API_VERSION

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


class VirtualMachineInstance(NamespacedResource):
    """
    Virtual Machine Instance object, inherited from Resource.
    Implements actions start / stop / status / wait for VM status / is running
    """
    api_version = API_VERSION

    def _to_dict(self):
        res = super()._to_dict()
        res["spec"] = get_base_vmi_spec()
        return res

    @property
    def interfaces(self):
        return self.instance.status.interfaces

    def virt_launcher_pod(self):
        """
        Get VMi virt-launcher Pod

        Returns:
            Pod: virt-launcher Pod
        """
        uid = self.instance.metadata.uid
        return list(Pod.get(
            dyn_client=self.client,
            namespace=self.namespace,
            label_selector=f'kubevirt.io=virt-launcher,kubevirt.io/created-by={uid}'
        ))[0]

    def wait_until_running(self, timeout=120, logs=True):
        """
        Wait until VMI is running

        Args:
            timeout (int): Time to wait for VMI.
            logs (bool): True to extract logs from the VMI pod and from the VMI.

        Returns:
            bool: True if VMI is running, False if not.
        """
        if not self.wait_for_status(status='Running', timeout=timeout):
            if not logs:
                return False

            virt_pod = self.virt_launcher_pod()
            if virt_pod:
                LOGGER.debug(f"{virt_pod.name} *****LOGS*****")
                LOGGER.debug(virt_pod.log(container="compute"))

            return False
        return True


class VirtualMachineInstanceMigration(NamespacedResource):
    api_version = API_VERSION

    def __init__(self, name, namespace, vmi, client=None):
        super().__init__(name=name, namespace=namespace, client=client)
        self._vmi = vmi

    def _to_dict(self):
        res = super()._to_dict()
        res["spec"] = {
            "vmiName": self._vmi.name
        }
        return res
