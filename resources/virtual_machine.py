# -*- coding: utf-8 -*-

import logging

from autologs.autologs import generate_logs

from utilities import types, utils

from .resource import SLEEP, TIMEOUT, Resource

LOGGER = logging.getLogger(__name__)


class VirtualMachine(Resource):
    """
    Virtual Machine object, inherited from Resource.
    Implements actions start / stop / status / wait for VM status / is running
    """

    def __init__(self, name, namespace=None):
        super(VirtualMachine, self).__init__()
        self.name = name
        self.namespace = namespace
        self.api_version = types.CNV_API_VERSION
        self.kind = types.VM

    @generate_logs()
    def start(self, timeout=TIMEOUT, sleep=SLEEP, wait=False):
        """
        Start VM with virtctl
        Args:
            timeout (int): Time to wait for the resource.
            sleep (int): Time to sleep between retries.
            wait (bool): If True wait else Not

        Returns:
            True if VM started, else False

        """
        res = utils.run_virtctl_command(command="start", namespace=self.namespace)[0]
        if wait and res:
            return self.wait_for_status(sleep=sleep, timeout=timeout, status=True)
        return res

    @generate_logs()
    def stop(self, timeout=TIMEOUT, sleep=SLEEP, wait=False):
        """
        Stop VM with virtctl
        Args:
            timeout (int): Time to wait for the resource.
            sleep (int): Time to sleep between retries.
            wait (bool): If True wait else Not

        Returns:
            bool: True if VM stopped, else False

        """
        res = utils.run_virtctl_command(command="stop", namespace=self.namespace)[0]
        if wait and res:
            return self.wait_for_status(sleep=sleep, timeout=timeout, status=False)
        return res

    @generate_logs()
    def wait_for_status(self, status, timeout=TIMEOUT, **kwargs):
        """
        Wait for resource to be in status

        Args:
            status (bool): Expected status(True vm is running, False vm is not running).
            timeout (int): Time to wait for the resource.

        Keyword Args:
            pretty
            _continue
            include_uninitialized
            field_selector
            label_selector
            limit
            resource_version
            timeout_seconds
            watch
            async_req

        Returns:
            bool: True if resource in desire status, False if timeout reached.
        """
        resources = self.list(**kwargs)
        for rsc in resources.watch(namespace=self.namespace, timeout=timeout, **kwargs):
            if rsc.get('raw_object', {}).get('spec', {}).get('running') == status:
                return True
        return False

    def node(self):
        """
        Get the node name where the VM is running

        Returns:
            str: Node name
        """
        return self.get().status.nodeName
