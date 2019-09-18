"""
Test VM restart
"""

import pytest
from tests import utils as test_utils
from utilities import console


@pytest.fixture(scope="module", autouse=True)
def restart_test_namespace(unprivileged_client):
    yield from test_utils.create_ns(client=unprivileged_client, name="restart-test")


@pytest.fixture()
def vm_to_restart(unprivileged_client, restart_test_namespace):
    with test_utils.VirtualMachineForTests(
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
    test_utils.wait_for_vm_interfaces(vm_to_restart.vmi)
    test_utils.vm_console_run_commands(
        console.Fedora, vm_to_restart, ["cat /proc/cmdline"]
    )
