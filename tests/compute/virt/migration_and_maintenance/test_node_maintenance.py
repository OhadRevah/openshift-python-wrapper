"""
 Draining node by Node Maintenance Operator
"""

import logging
import random
from contextlib import contextmanager
from subprocess import run

import pytest
from pytest_testconfig import config as py_config
from resources.node_maintenance import NodeMaintenance
from resources.virtual_machine import VirtualMachineInstanceMigration
from tests.compute import utils as compute_utils
from tests.compute.virt import utils as virt_utils
from utilities import console
from utilities.infra import Images
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    WinRMcliPod,
    fedora_vm_body,
)


LOGGER = logging.getLogger(__name__)


@contextmanager
def running_sleep_in_linux(vm_cli):
    process = "sleep 1000"
    with vm_cli as vm_console:
        vm_console.sendline(f"nohup {process} &")
        vm_console.expect("nohup: ")
    yield
    with vm_cli as vm_console:
        vm_console.sendline(f'ps aux | grep "{process}" | grep -v grep | wc -l')
        vm_console.expect("1")


@contextmanager
def drain_node_console(node):
    try:
        LOGGER.info(f"Drain the node {node.name}")
        run(
            f"nohup oc adm drain {node.name} --delete-local-data --ignore-daemonsets=true &",
            shell=True,
        )
        yield
    finally:
        LOGGER.info(f"Uncordon node {node.name}")
        run(f"oc adm uncordon {node.name}", shell=True)


def drain_using_console(dyn_client, source_node, source_pod, vm, vm_cli):
    with running_sleep_in_linux(vm_cli=vm_cli):
        with drain_node_console(node=source_node):
            check_draining_process(dyn_client=dyn_client, source_pod=source_pod, vm=vm)
        virt_utils.wait_for_node_schedulable_status(node=source_node, status=True)


def drain_using_console_windows(
    dyn_client,
    source_node,
    source_pod,
    vm,
    winrmcli_pod,
    helper_vm=False,
):
    process_name = "mspaint.exe"
    pre_migrate_processid = compute_utils.start_and_fetch_processid_on_windows_vm(
        vm=vm,
        winrmcli_pod=winrmcli_pod,
        process_name=process_name,
        helper_vm=helper_vm,
    )
    with drain_node_console(node=source_node):
        check_draining_process(dyn_client=dyn_client, source_pod=source_pod, vm=vm)
        post_migrate_processid = compute_utils.fetch_processid_from_windows_vm(
            vm=vm,
            winrmcli_pod=winrmcli_pod,
            process_name=process_name,
            helper_vm=helper_vm,
        )
        assert (
            post_migrate_processid == pre_migrate_processid
        ), f"Post migrate processid is: {post_migrate_processid}. Pre migrate processid is: {pre_migrate_processid}"

    virt_utils.wait_for_node_schedulable_status(
        node=vm.vmi.virt_launcher_pod.node,
        status=True,
    )


@pytest.fixture()
def vm_container_disk_fedora(namespace, unprivileged_client):
    name = f"vm-nodemaintenance-{random.randrange(99999)}"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        eviction=True,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.fixture()
def winrmcli_pod(
    rhel7_workers,
    vm_instance_from_template_multi_storage_scope_function,
    schedulable_nodes,
):
    # For RHEL7 workers, helper_vm is used
    if rhel7_workers:
        yield
    else:
        # For node maintenance tests winrmcli-pod and VMI should be located on different nodes
        node_for_winrmcli = list(
            filter(
                lambda n: n.name
                != vm_instance_from_template_multi_storage_scope_function.vmi.virt_launcher_pod.node.name,
                schedulable_nodes,
            )
        )
        assert len(node_for_winrmcli) > 0, "No available nodes for winrmcli pod"

        with WinRMcliPod(
            name="winrmcli-pod",
            namespace=vm_instance_from_template_multi_storage_scope_function.namespace,
            node_selector=node_for_winrmcli[0].name,
        ) as winrm_pod:
            winrm_pod.wait_for_status(status=winrm_pod.Status.RUNNING, timeout=60)
            yield winrm_pod


def check_draining_process(dyn_client, source_pod, vm):
    source_node = source_pod.node
    virt_utils.wait_for_node_schedulable_status(node=source_node, status=False)
    for migration_job in VirtualMachineInstanceMigration.get(dyn_client):
        if migration_job.instance.spec.vmiName == vm.name:
            migration_job.wait_for_status(
                status=migration_job.Status.SUCCEEDED, timeout=1800
            )

    source_pod.wait_deleted()
    target_node = vm.vmi.virt_launcher_pod.node
    assert target_node != source_node, "Source Node and Target Node should be different"


@pytest.mark.polarion("CNV-3006")
def test_node_drain_using_console_fedora(
    skip_when_one_node,
    admin_client,
    vm_container_disk_fedora,
):

    drain_using_console(
        dyn_client=admin_client,
        source_node=vm_container_disk_fedora.vmi.virt_launcher_pod.node,
        source_pod=vm_container_disk_fedora.vmi.virt_launcher_pod,
        vm=vm_container_disk_fedora,
        vm_cli=console.Fedora(vm_container_disk_fedora),
    )


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_class, vm_instance_from_template_multi_storage_scope_class",
    [
        pytest.param(
            {
                "dv_name": "dv-rhel8-template-node-maintenance",
                "image": f"{Images.Rhel.DIR}/{Images.Rhel.RHEL8_0_IMG}",
            },
            {
                "vm_name": "rhel8-template-node-maintenance",
                "template_labels": {
                    "os": "rhel8.0",
                    "workload": "server",
                    "flavor": "tiny",
                },
            },
        )
    ],
    indirect=True,
)
@pytest.mark.usefixtures(
    "skip_when_one_node",
    "skip_migration_access_mode_rwo",
    "data_volume_multi_storage_scope_class",
)
class TestNodeMaintenanceRHEL:
    @pytest.mark.polarion("CNV-2286")
    def test_node_maintenance_job_rhel(
        self, vm_instance_from_template_multi_storage_scope_class, admin_client
    ):
        source_pod = (
            vm_instance_from_template_multi_storage_scope_class.vmi.virt_launcher_pod
        )
        source_node = source_pod.node

        with running_sleep_in_linux(
            vm_cli=console.RHEL(vm=vm_instance_from_template_multi_storage_scope_class)
        ):
            with NodeMaintenance(
                name="node-maintenance-job", node=source_node, timeout=600
            ) as nm:
                nm.wait_for_status(status=nm.Status.RUNNING)
                check_draining_process(
                    dyn_client=admin_client,
                    source_pod=source_pod,
                    vm=vm_instance_from_template_multi_storage_scope_class,
                )
                nm.wait_for_status(status=nm.Status.SUCCEEDED, timeout=360)
            virt_utils.wait_for_node_schedulable_status(node=source_node, status=True)

    @pytest.mark.polarion("CNV-2292")
    def test_node_drain_using_console_rhel(
        self, vm_instance_from_template_multi_storage_scope_class, admin_client
    ):
        drain_using_console(
            dyn_client=admin_client,
            source_node=vm_instance_from_template_multi_storage_scope_class.vmi.virt_launcher_pod.node,
            source_pod=vm_instance_from_template_multi_storage_scope_class.vmi.virt_launcher_pod,
            vm=vm_instance_from_template_multi_storage_scope_class,
            vm_cli=console.RHEL(vm=vm_instance_from_template_multi_storage_scope_class),
        )


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function, vm_instance_from_template_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-windows-template-node-maintenance",
                "image": py_config["latest_windows_version"]["image_path"],
            },
            {
                "vm_name": "windows-template-node-maintenance",
                "template_labels": py_config["latest_windows_version"][
                    "template_labels"
                ],
                "cpu_threads": 2,
            },
            marks=pytest.mark.polarion("CNV-2048"),
        ),
    ],
    indirect=True,
)
def test_node_drain_template_windows(
    skip_when_one_node,
    skip_migration_access_mode_rwo,
    data_volume_multi_storage_scope_function,
    vm_instance_from_template_multi_storage_scope_function,
    winrmcli_pod,
    bridge_attached_helper_vm,
    admin_client,
):
    drain_using_console_windows(
        dyn_client=admin_client,
        source_node=vm_instance_from_template_multi_storage_scope_function.vmi.virt_launcher_pod.node,
        source_pod=vm_instance_from_template_multi_storage_scope_function.vmi.virt_launcher_pod,
        vm=vm_instance_from_template_multi_storage_scope_function,
        winrmcli_pod=winrmcli_pod,
        helper_vm=bridge_attached_helper_vm,
    )
