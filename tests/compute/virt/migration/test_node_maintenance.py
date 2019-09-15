"""
 Draining node by Node Maintenance Operator
"""

from contextlib import contextmanager

import pytest
from resources.node_maintenance import NodeMaintenance
from resources.virtual_machine import (
    VirtualMachineInstance,
    VirtualMachineInstanceMigration,
)
from tests import utils as test_utils
from tests.compute.virt import utils as virt_utils
from utilities import console


@contextmanager
def running_sleep_in_guest(vm):
    process = "sleep 1000"
    with console.Fedora(vm) as vm_console:
        vm_console.sendline(f"nohup {process} &")
        vm_console.expect("nohup: ")
    yield
    with console.Fedora(vm) as vm_console:
        vm_console.sendline(f'ps aux | grep "{process}" | grep -v grep | wc -l')
        vm_console.expect("1")


@pytest.fixture(scope="module")
def skip_when_other_vmi_present(default_client):
    if list(VirtualMachineInstance.get(default_client)):
        pytest.skip(msg="Can't work when other VMI present")


@pytest.fixture()
def vm0(virt_namespace):
    with test_utils.VirtualMachineForTests(
        name="vm-node-maintenance", namespace=virt_namespace.name, eviction=True
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.mark.polarion("CNV-2286")
def test_node_maintenance(
    skip_when_other_vmi_present, skip_when_one_node, vm0, default_client
):

    source_pod = vm0.vmi.virt_launcher_pod
    source_node = source_pod.node

    with running_sleep_in_guest(vm0):
        with NodeMaintenance(name="node-maintenance-job", node=source_node):
            virt_utils.wait_for_node_unschedulable_status(node=source_node, status=True)

            for migration_job in VirtualMachineInstanceMigration.get(default_client):
                if migration_job.instance.spec.vmiName == vm0.name:
                    migration_job.wait_for_status(status="Succeeded", timeout=600)

            source_pod.wait_deleted()
            target_node = vm0.vmi.virt_launcher_pod.node
            assert (
                target_node != source_node
            ), "Source Node and Target Node should be different"
        virt_utils.wait_for_node_unschedulable_status(node=source_node, status=False)
