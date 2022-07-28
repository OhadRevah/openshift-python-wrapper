import logging
import shlex
from contextlib import contextmanager

from ocp_resources.utils import TimeoutExpiredError

from tests.compute.utils import (
    fetch_processid_from_linux_vm,
    kill_processes_by_name_linux,
    start_and_fetch_processid_on_linux_vm,
    update_hco_annotations,
)
from utilities.infra import run_ssh_commands
from utilities.virt import (
    migrate_vm_and_verify,
    verify_vm_migrated,
    wait_for_migration_finished,
    wait_for_updated_kv_value,
)


LOGGER = logging.getLogger(__name__)


class NodeMaintenanceException(Exception):
    def __init__(self, node, action, error):
        self.node = node
        self.action = action
        self.error = error

    def __str__(self):
        return f"{self.action} node maintenance failed: {self.node.name} - {self.error}"


@contextmanager
def running_sleep_in_linux(vm):
    process = "sleep"
    kill_processes_by_name_linux(vm=vm, process_name=process, check_rc=False)
    pid_orig = start_and_fetch_processid_on_linux_vm(
        vm=vm, process_name=process, args="1000", use_nohup=True
    )
    yield
    pid_after = fetch_processid_from_linux_vm(
        vm=vm, process_name=process, fail_if_process_not_found=True
    )
    kill_processes_by_name_linux(vm=vm, process_name=process)
    assert pid_orig == pid_after, f"PID mismatch: {pid_orig} != {pid_after}"


@contextmanager
def append_feature_gate_to_hco(feature_gate, resource, client, namespace):
    with update_hco_annotations(
        resource=resource,
        path="developerConfiguration/featureGates",
        value=feature_gate,
    ):
        wait_for_updated_kv_value(
            admin_client=client,
            hco_namespace=namespace,
            path=[
                "developerConfiguration",
                "featureGates",
            ],
            value=feature_gate,
        )
        yield


def migrate_and_verify_multi_vms(vm_list):
    vms_dict = {}
    failed_migrations_list = []

    for vm in vm_list:
        vms_dict[vm.name] = {
            "node_before": vm.vmi.node,
            "vmi_source_pod": vm.vmi.virt_launcher_pod,
            "vm_mig": migrate_vm_and_verify(vm=vm, wait_for_migration_success=False),
        }

    for vm in vm_list:
        migration = vms_dict[vm.name]["vm_mig"]
        wait_for_migration_finished(vm=vm, migration=migration)
        migration.clean_up()

    for vm in vm_list:
        vm_sources = vms_dict[vm.name]
        try:
            verify_vm_migrated(
                vm=vm,
                node_before=vm_sources["node_before"],
                vmi_source_pod=vm_sources["vmi_source_pod"],
            )
        except (AssertionError, TimeoutExpiredError):
            failed_migrations_list.append(vm.name)

    assert (
        not failed_migrations_list
    ), f"Some VMs failed to migrate - {failed_migrations_list}"


def get_stress_ng_pid(ssh_exec):
    stress = "stress-ng"
    LOGGER.info(f"Get pid of {stress}")
    return run_ssh_commands(
        host=ssh_exec,
        commands=shlex.split(f"pgrep {stress}"),
    )[0]
