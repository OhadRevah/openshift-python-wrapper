# -*- coding: utf-8 -*-

import logging

from openshift.dynamic.exceptions import NotFoundError
from resources.utils import TimeoutSampler
from utilities import console
from utilities.virt import vm_console_run_commands, wait_for_vm_interfaces


LOGGER = logging.getLogger(__name__)


def vm_started(vm, wait_for_interfaces=True):
    """ Start a VM and wait for its status to be 'Running'

    If wait_for_interfaces - wait for interfaces to be up.
    """

    vm.start(wait=True)
    vm.vmi.wait_until_running()
    if wait_for_interfaces:
        wait_for_vm_interfaces(vm.vmi)


def wait_for_windows_vm(vm, version, winrmcli_pod):
    """
    Samples Windows VM; wait for it to complete the boot process.
    """

    LOGGER.info(
        f"Windows VM {vm.name} booting up, "
        f"will attempt to access it up to 25 minutes."
    )

    vmi_ipaddr = vm.vmi.virt_launcher_pod.instance.status.podIP
    command = [
        "bash",
        "-c",
        f"/bin/winrm-cli -hostname {vmi_ipaddr} \
        -username Administrator -password Heslo123 \
        'wmic os get Caption /value'",
    ]

    sampler = TimeoutSampler(
        timeout=1500, sleep=15, func=winrmcli_pod.execute, command=command,
    )
    for sample in sampler:
        if version in str(sample):
            return True


def vm_os_version(vm):
    """ Verify VM os version using console """

    command = [f"cat /etc/redhat-release | grep {vm.name.split('-')[-1]} | wc -l"]

    vm_console_run_commands(console_impl=console.RHEL, vm=vm, commands=command)


def vm_deleted(vm):
    try:
        vm.delete(wait=True)
        return True
    except NotFoundError:
        return False
