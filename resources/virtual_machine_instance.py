# -*- coding: utf-8 -*-

import logging

from .pod import Pod
from .resource import NamespacedResource

LOGGER = logging.getLogger(__name__)


class VirtualMachineInstance(NamespacedResource):
    """
    Virtual Machine Instance object, inherited from Resource.
    Implements actions start / stop / status / wait for VM status / is running
    """
    api_version = 'kubevirt.io/v1alpha3'

    def _to_dict(self):
        res = super()._to_dict()
        res["spec"] = {
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
            LOGGER.error(f"{self.kind} {self.name} failed to run")
            if not logs:
                return False

            virt_pod = self.virt_launcher_pod()
            if virt_pod:
                LOGGER.debug(f"{virt_pod.name} *****LOGS*****")
                LOGGER.debug(virt_pod.log(container="compute"))

            return False
        return True
