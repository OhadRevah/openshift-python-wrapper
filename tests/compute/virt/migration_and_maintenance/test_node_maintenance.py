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
from resources.utils import TimeoutSampler
from resources.virtual_machine import VirtualMachineInstanceMigration
from tests.compute.virt import utils as virt_utils
from utilities import console
from utilities.infra import Images
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    WinRMcliPod,
    execute_winrm_cmd,
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
        LOGGER.info(f"Cordon node {node.name}")
        run(
            f"nohup oc adm drain {node.name} --delete-local-data --ignore-daemonsets=true --force &",
            shell=True,
        )
        yield
    finally:
        LOGGER.info(f"Uncordon node {node.name}")
        run(f"oc adm uncordon {node.name}", shell=True)


def drain_using_console(default_client, source_node, source_pod, vm, vm_cli):
    with running_sleep_in_linux(vm_cli=vm_cli):
        with drain_node_console(node=source_node):
            check_draining_process(
                default_client=default_client, source_pod=source_pod, vm=vm
            )
        virt_utils.wait_for_node_schedulable_status(node=source_node, status=True)


def drain_using_console_windows(
    default_client,
    source_node,
    source_pod,
    vm,
    winrmcli_pod,
    windows_initial_boot_time,
    helper_vm=False,
):

    with drain_node_console(node=source_node):
        check_draining_process(
            default_client=default_client, source_pod=source_pod, vm=vm
        )
        boot_time_after_migration = check_windows_boot_time(
            vm=vm, winrmcli_pod=winrmcli_pod, helper_vm=helper_vm
        )
        LOGGER.info(f"Windows boot time after migration: {boot_time_after_migration}")
        assert (
            boot_time_after_migration == windows_initial_boot_time
        ), f"Initial time: {windows_initial_boot_time}. Time after migration: {boot_time_after_migration}"

    virt_utils.wait_for_node_schedulable_status(
        node=vm.vmi.virt_launcher_pod.node, status=True,
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
def windows_initial_boot_time(
    vm_instance_from_template_multi_storage_scope_function,
    winrmcli_pod,
    bridge_attached_helper_vm,
):
    LOGGER.info(
        f"Windows VM {vm_instance_from_template_multi_storage_scope_function.vmi.name} "
        f"is booting up, it may take up to 20 minutess."
    )
    boot_time = check_windows_boot_time(
        vm=vm_instance_from_template_multi_storage_scope_function,
        winrmcli_pod=winrmcli_pod,
        helper_vm=bridge_attached_helper_vm,
    )
    LOGGER.info(f"VM initial boot time: {boot_time}")
    yield boot_time


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


def check_windows_boot_time(vm, winrmcli_pod, timeout=1200, helper_vm=False):
    pod_output_samples = TimeoutSampler(
        timeout=timeout,
        sleep=15,
        func=execute_winrm_cmd,
        vmi_ip=vm.vmi.virt_launcher_pod.instance.status.podIP,
        winrmcli_pod=winrmcli_pod,
        target_vm=vm,
        helper_vm=helper_vm,
        cmd="wmic os get lastbootuptime",
    )

    for pod_output in pod_output_samples:
        if "LastBootUpTime" in str(pod_output):
            return str(pod_output)


def check_draining_process(default_client, source_pod, vm):
    source_node = source_pod.node
    virt_utils.wait_for_node_schedulable_status(node=source_node, status=False)
    for migration_job in VirtualMachineInstanceMigration.get(default_client):
        if migration_job.instance.spec.vmiName == vm.name:
            migration_job.wait_for_status(
                status=migration_job.Status.SUCCEEDED, timeout=900
            )

    source_pod.wait_deleted()
    target_node = vm.vmi.virt_launcher_pod.node
    assert target_node != source_node, "Source Node and Target Node should be different"


@pytest.mark.polarion("CNV-3006")
def test_node_drain_using_console_fedora(
    skip_when_one_node, default_client, vm_container_disk_fedora,
):

    drain_using_console(
        default_client=default_client,
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
        self, vm_instance_from_template_multi_storage_scope_class, default_client
    ):
        source_pod = (
            vm_instance_from_template_multi_storage_scope_class.vmi.virt_launcher_pod
        )
        source_node = source_pod.node

        with running_sleep_in_linux(
            vm_cli=console.RHEL(vm=vm_instance_from_template_multi_storage_scope_class)
        ):
            with NodeMaintenance(name="node-maintenance-job", node=source_node) as nm:
                nm.wait_for_status(status=nm.Status.RUNNING)
                check_draining_process(
                    default_client=default_client,
                    source_pod=source_pod,
                    vm=vm_instance_from_template_multi_storage_scope_class,
                )
                nm.wait_for_status(status=nm.Status.SUCCEEDED)
            virt_utils.wait_for_node_schedulable_status(node=source_node, status=True)

    @pytest.mark.polarion("CNV-2292")
    def test_node_drain_using_console_rhel(
        self, vm_instance_from_template_multi_storage_scope_class, default_client
    ):
        drain_using_console(
            default_client=default_client,
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
    windows_initial_boot_time,
    default_client,
):
    drain_using_console_windows(
        default_client=default_client,
        source_node=vm_instance_from_template_multi_storage_scope_function.vmi.virt_launcher_pod.node,
        source_pod=vm_instance_from_template_multi_storage_scope_function.vmi.virt_launcher_pod,
        vm=vm_instance_from_template_multi_storage_scope_function,
        winrmcli_pod=winrmcli_pod,
        windows_initial_boot_time=windows_initial_boot_time,
        helper_vm=bridge_attached_helper_vm,
    )
