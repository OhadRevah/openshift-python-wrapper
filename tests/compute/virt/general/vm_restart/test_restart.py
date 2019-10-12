"""
Test VM restart
"""
import logging

import pytest
from utilities import console
from utilities.infra import create_ns
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    vm_console_run_commands,
    wait_for_vm_interfaces,
)


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module", autouse=True)
def restart_test_namespace(unprivileged_client):
    yield from create_ns(client=unprivileged_client, name="restart-test")


@pytest.fixture()
def vm_to_restart(unprivileged_client, restart_test_namespace):
    name = "vmi-to-restart"
    with VirtualMachineForTests(
        client=unprivileged_client,
        name=name,
        namespace=restart_test_namespace.name,
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
    vm_to_restart.vmi.wait_until_running()
    LOGGER.info("VM is running: Stopping VM")
    vm_to_restart.stop(wait=True)
    LOGGER.info("VM is stopped: Starting VM")
    vm_to_restart.start(wait=True)
    vm_to_restart.vmi.wait_until_running()
    wait_for_vm_interfaces(vm_to_restart.vmi)
    vm_console_run_commands(console.Fedora, vm_to_restart, ["cat /proc/cmdline"])
