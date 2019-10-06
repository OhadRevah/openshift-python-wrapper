"""
Test VM restart
"""

import pytest
from utilities import console
from utilities.infra import create_ns
from utilities.virt import (
    VirtualMachineForTests,
    vm_console_run_commands,
    wait_for_vm_interfaces,
)


@pytest.fixture(scope="module", autouse=True)
def restart_test_namespace(unprivileged_client):
    yield from create_ns(client=unprivileged_client, name="restart-test")


@pytest.fixture()
def vm_to_restart(unprivileged_client, restart_test_namespace):
    with VirtualMachineForTests(
        client=unprivileged_client,
        name="vmi-to-restart",
        namespace=restart_test_namespace.name,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.mark.polarion("CNV-1497")
def test_vm_restart(vm_to_restart):
    # now the VM was started and running
    vm_to_restart.restart(wait=True)
    vm_to_restart.vmi.wait_until_running()
    # required by testplan
    vm_to_restart.stop(wait=True)
    # required by testplan
    vm_to_restart.start(wait=True)
    vm_to_restart.vmi.wait_until_running()
    # we just need to run something trivial to doublecheck the VM
    # is really running
    wait_for_vm_interfaces(vm_to_restart.vmi)
    vm_console_run_commands(console.Fedora, vm_to_restart, ["cat /proc/cmdline"])
