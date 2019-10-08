"""
 Draining node by Node Maintenance Operator
"""

import random
from contextlib import contextmanager
from subprocess import run

import pytest
from resources.node_maintenance import NodeMaintenance
from resources.virtual_machine import (
    VirtualMachineInstance,
    VirtualMachineInstanceMigration,
)
from tests.compute.virt import utils as virt_utils
from utilities import console
from utilities.virt import VirtualMachineForTests, fedora_vm_body


@contextmanager
def running_sleep_in_fedora(vm):
    process = "sleep 1000"
    with console.Fedora(vm) as vm_console:
        vm_console.sendline(f"nohup {process} &")
        vm_console.expect("nohup: ")
    yield
    with console.Fedora(vm) as vm_console:
        vm_console.sendline(f'ps aux | grep "{process}" | grep -v grep | wc -l')
        vm_console.expect("1")


@contextmanager
def drain_node_console(node):
    try:
        run(
            f"nohup oc adm drain {node.name} --delete-local-data --ignore-daemonsets=true --force &",
            shell=True,
        )
        yield
    finally:
        run(f"oc adm uncordon {node.name}", shell=True)


@pytest.fixture(scope="module")
def skip_when_other_vmi_present(default_client):
    if list(VirtualMachineInstance.get(default_client)):
        pytest.skip(msg="Can't work when other VMI present")


@pytest.fixture()
def vm0(virt_namespace):
    name = f"vm-nodemaintenance-{random.randrange(99999)}"
    with VirtualMachineForTests(
        name=name,
        namespace=virt_namespace.name,
        eviction=True,
        body=fedora_vm_body(name),
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


def check_draining_process(default_client, source_pod, vm):
    source_node = source_pod.node
    virt_utils.wait_for_node_unschedulable_status(node=source_node, status=True)
    for migration_job in VirtualMachineInstanceMigration.get(default_client):
        if migration_job.instance.spec.vmiName == vm.name:
            migration_job.wait_for_status(
                status=migration_job.Status.SUCCEEDED, timeout=600
            )

    source_pod.wait_deleted()
    target_node = vm.vmi.virt_launcher_pod.node
    assert target_node != source_node, "Source Node and Target Node should be different"


@pytest.mark.polarion("CNV-2286")
def test_node_maintenance_fedora(
    skip_when_other_vmi_present, skip_when_one_node, vm0, default_client
):
    source_pod = vm0.vmi.virt_launcher_pod
    source_node = source_pod.node

    with running_sleep_in_fedora(vm0):
        with NodeMaintenance(name="node-maintenance-job", node=source_node) as nm:
            nm.wait_for_status(status=nm.Status.RUNNING)
            check_draining_process(
                default_client=default_client, source_pod=source_pod, vm=vm0
            )
            nm.wait_for_status(status=nm.Status.SUCCEEDED)
        virt_utils.wait_for_node_unschedulable_status(node=source_node, status=False)


@pytest.mark.polarion("CNV-3006")
def test_node_drain_console(
    skip_when_other_vmi_present, skip_when_one_node, vm0, default_client
):
    source_pod = vm0.vmi.virt_launcher_pod
    source_node = source_pod.node

    with running_sleep_in_fedora(vm0):
        with drain_node_console(node=source_node):
            check_draining_process(
                default_client=default_client, source_pod=source_pod, vm=vm0
            )
        virt_utils.wait_for_node_unschedulable_status(node=source_node, status=False)
