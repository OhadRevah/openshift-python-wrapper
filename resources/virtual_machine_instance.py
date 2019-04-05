# -*- coding: utf-8 -*-

import logging
import re

from utilities import types
from .resource import Resource
from .pod import Pod

LOGGER = logging.getLogger(__name__)


class VirtualMachineInstance(Resource):
    """
    Virtual Machine object, inherited from Resource.
    Implements actions start / stop / status / wait for VM status / is running
    """
    def __init__(self, name, namespace=None):
        super(VirtualMachineInstance, self).__init__()
        self.name = name
        self.namespace = namespace
        self.api_version = types.CNV_API_VERSION
        self.kind = types.VMI

    def virt_launcher_pod(self):
        """
        Get VMi virt-launcher Pod

        Returns:
            str: virt-launcher Pod name
        """
        pod = Pod(namespace=self.namespace)
        return pod.search(regex=re.compile(rf'virt-launcher-{self.name}-\w+'))

    def running(self, logs=True):
        """
        Check if VMI is running

        Args:
            logs (bool): True to extract logs from the VMI pod and from the VMI.

        Returns:
            bool: True if VMI is running, False if not.
        """
        if not self.wait_for_status(status=types.RUNNING):
            LOGGER.error("VMi {self.name} failed to run")
            if not logs:
                return False

            virt_pod = self.virt_launcher_pod()
            if virt_pod:
                virt_pod_obj = Pod(name=virt_pod, namespace=self.namespace)
                LOGGER.debug(f"{virt_pod} *****LOGS*****")
                LOGGER.debug(virt_pod_obj.logs(container="compute"))

            LOGGER.debug(f"{self.name} *****LOGS*****")
            LOGGER.debug(self.logs())
            return False
        return True
