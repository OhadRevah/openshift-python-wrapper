# -*- coding: utf-8 -*-

import logging
import re

from .pod import Pod
from .resource import NamespacedResource

LOGGER = logging.getLogger(__name__)


class VirtualMachineInstance(NamespacedResource):
    """
    Virtual Machine Instance object, inherited from Resource.
    Implements actions start / stop / status / wait for VM status / is running
    """
    api_version = 'kubevirt.io/v1alpha3'
    kind = 'VirtualMachineInstance'

    def __init__(self, name, namespace=None):
        super(VirtualMachineInstance, self).__init__(name=name, namespace=namespace)

    def virt_launcher_pod(self):
        """
        Get VMi virt-launcher Pod

        Returns:
            Pod: virt-launcher Pod
        """
        pod_resource = Pod(namespace=self.namespace)
        return pod_resource.search(
            regex=re.compile(rf'virt-launcher-{self.name}-\w+')
        )

    def running(self, logs=True):
        """
        Check if VMI is running

        Args:
            logs (bool): True to extract logs from the VMI pod and from the VMI.

        Returns:
            bool: True if VMI is running, False if not.
        """
        if not self.wait_for_status(status='Running'):
            LOGGER.error(f"{self.kind} {self.name} failed to run")
            if not logs:
                return False

            virt_pod = self.virt_launcher_pod()
            if virt_pod:
                LOGGER.debug(f"{virt_pod.name} *****LOGS*****")
                LOGGER.debug(virt_pod.logs(container="compute"))

            LOGGER.debug(f"{self.name} *****LOGS*****")
            LOGGER.debug(self.logs())
            return False
        return True

    def search(self, regex):
        """
        Search for VirtualMachineInstance

        Args:
            regex (re.compile): re.compile regex to search

        Returns:
            Resource: VirtualMachineInstance or None
        """
        all_ = self.list_names()
        res = [r for r in all_ if regex.findall(r)]
        if res:
            return VirtualMachineInstance(
                name=res[0],
                namespace=self.namespace,
            )
        return None
