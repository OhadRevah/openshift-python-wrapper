"""
Test VM restart
"""
import logging

import pytest
from utilities import console
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    vm_console_run_commands,
    wait_for_vm_interfaces,
)


LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def vm_to_restart(unprivileged_client, namespace):
    name = "vmi-to-restart"
    with VirtualMachineForTests(
        client=unprivileged_client,
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.mark.polarion("CNV-1497")
def test_vm_restart(vm_to_restart):
    LOGGER.info("VM is running: Restarting VM")
    vm_to_restart.restart(wait=True)
    LOGGER.info("VM is running: Stopping VM")
    vm_to_restart.stop(wait=True)
    LOGGER.info("VM is stopped: Starting VM")
    vm_to_restart.start(wait=True)
    vm_to_restart.vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vm_to_restart.vmi)
    vm_console_run_commands(
        console_impl=console.Fedora, vm=vm_to_restart, commands=["cat /proc/cmdline"]
    )
