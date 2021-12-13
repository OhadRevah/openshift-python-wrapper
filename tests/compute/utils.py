# -*- coding: utf-8 -*-
import logging
import shlex
from contextlib import contextmanager

from benedict import benedict
from ocp_resources.resource import ResourceEditor
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler

from utilities.hco import get_hyperconverged_resource
from utilities.infra import hco_cr_jsonpatch_annotations_dict, run_ssh_commands
from utilities.virt import (
    get_kubevirt_hyperconverged_spec,
    migrate_vm_and_verify,
    wait_for_ssh_connectivity,
)


LOGGER = logging.getLogger(__name__)
OS_PROC_NAME = {"linux": "ping", "windows": "mspaint.exe"}


def get_linux_timezone(ssh_exec):
    return run_ssh_commands(
        host=ssh_exec, commands=shlex.split("timedatectl show | grep -i timezone")
    )[0]


def get_windows_timezone(ssh_exec, get_standard_name=False):
    """
    Args:
        ssh_exec: vm SSH executor
        get_standard_name (bool, default False): If True, get only Windows StandardName
    """
    standard_name_cmd = '| findstr "StandardName"' if get_standard_name else ""
    timezone_cmd = shlex.split(
        f'powershell -command "Get-TimeZone {standard_name_cmd}"'
    )
    return run_ssh_commands(host=ssh_exec, commands=[timezone_cmd])[0]


def start_and_fetch_processid_on_windows_vm(vm, process_name):
    wait_for_ssh_connectivity(vm=vm)
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split(f"wmic process call create {process_name}"),
    )
    return fetch_processid_from_windows_vm(vm=vm, process_name=process_name)


def fetch_processid_from_windows_vm(vm, process_name):
    cmd = shlex.split(
        fr"wmic process where (Name=\'{process_name}\') get processid /value"
    )
    return run_ssh_commands(host=vm.ssh_exec, commands=cmd)[0]


def validate_pause_optional_migrate_unpause_windows_vm(
    vm, pre_pause_pid=None, migrate=False
):
    proc_name = OS_PROC_NAME["windows"]
    if not pre_pause_pid or not pre_pause_pid.isnumeric():
        pre_pause_pid = start_and_fetch_processid_on_windows_vm(
            vm=vm, process_name=proc_name
        )
    pause_optional_migrate_unpause_and_check_connectivity(vm=vm, migrate=migrate)
    post_pause_pid = fetch_processid_from_windows_vm(vm=vm, process_name=proc_name)
    kill_processes_by_name_windows(vm=vm, process_name=proc_name)
    assert (
        post_pause_pid == pre_pause_pid
    ), f"PID mismatch!\nPre pause PID is: {pre_pause_pid}\nPost pause PID is: {post_pause_pid}"


def start_and_fetch_processid_on_linux_vm(vm, process_name, args=""):
    wait_for_ssh_connectivity(vm=vm)
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split(f"{process_name} {args} </dev/null &>/dev/null &"),
    )
    return fetch_processid_from_linux_vm(vm=vm, process_name=process_name)


def fetch_processid_from_linux_vm(vm, process_name):
    return run_ssh_commands(
        host=vm.ssh_exec,
        commands=["bash", "-c", f"`which pidof` '{process_name}' || true"],
    )[0]


def pause_optional_migrate_unpause_and_check_connectivity(vm, migrate=False):
    vm.vmi.pause(wait=True)
    if migrate:
        migrate_vm_and_verify(
            vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False
        )
    vm.vmi.unpause(wait=True)
    wait_for_ssh_connectivity(vm=vm)


def validate_pause_optional_migrate_unpause_linux_vm(
    vm, pre_pause_pid=None, migrate=False
):
    proc_name = OS_PROC_NAME["linux"]
    if not pre_pause_pid or not pre_pause_pid.isnumeric():
        pre_pause_pid = start_and_fetch_processid_on_linux_vm(
            vm=vm, process_name=proc_name, args="localhost"
        )
    pause_optional_migrate_unpause_and_check_connectivity(vm=vm, migrate=migrate)
    post_pause_pid = fetch_processid_from_linux_vm(vm=vm, process_name=proc_name)
    kill_processes_by_name_linux(vm=vm, process_name=proc_name)
    assert (
        post_pause_pid == pre_pause_pid
    ), f"PID mismatch!\nPre pause PID is: {pre_pause_pid}\nPost pause PID is: {post_pause_pid}"


def validate_libvirt_persistent_domain(vm):
    domain = vm.vmi.virt_launcher_pod.execute(
        command=shlex.split("virsh list --persistent"), container="compute"
    )
    assert vm.vmi.Status.RUNNING.lower() in domain


def kill_processes_by_name_linux(vm, process_name):
    cmd = shlex.split(f"pkill {process_name}")
    run_ssh_commands(host=vm.ssh_exec, commands=cmd)


def kill_processes_by_name_windows(vm, process_name):
    cmd = shlex.split(f"taskkill /F /IM {process_name}")
    run_ssh_commands(host=vm.ssh_exec, commands=cmd)


@contextmanager
def update_hco_config(resource, path, value):
    jsonpatch_key = "kubevirt.kubevirt.io/jsonpatch"
    resource_existing_jsonpatch_annotation = resource.instance.metadata.get(
        "annotations", {}
    ).get(jsonpatch_key)
    hco_config_jsonpath_dict = hco_cr_jsonpatch_annotations_dict(
        component="kubevirt",
        path=path,
        value=value,
    )

    # Avoid overwriting existing jsonpatch annotations
    # example:
    # '[{"op": "add", "path": "/spec/configuration/machineType", "value": "pc-q35-rhel8.4.0"},
    # {"op": "add", "path": "/spec/configuration/cpuModel", "value": "Haswell-noTSX"}]]'
    if resource_existing_jsonpatch_annotation:
        hco_annotations_dict = hco_config_jsonpath_dict["metadata"]["annotations"]
        hco_annotations_dict[
            jsonpatch_key
        ] = f"{resource_existing_jsonpatch_annotation[:-1]},{hco_annotations_dict[jsonpatch_key][1:]}"

    editor = ResourceEditor(
        patches={
            resource: hco_config_jsonpath_dict,
        },
    )
    editor.update(backup_resources=True)
    yield
    editor.restore()


def wait_for_updated_kv_value(admin_client, hco_namespace, path, value, timeout=15):
    """
    Waits for updated values in KV CR configuration

    Args:
        admin_client (:obj:`DynamicClient`): DynamicClient object
        hco_namespace (:obj:`Namespace`): HCO namespace object
        path (list): list of nested keys to be looked up in KV CR configuration dict
        value (any): the expected value of the last key in path

    Example:
        path - ['minCPUModel'], value - 'Haswell-noTSX'
        {"configuration": {"minCPUModel": "Haswell-noTSX"}} will be matched against KV CR spec.

    Raises:
        TimeoutExpiredError: After timeout is reached if the expected key value does not match the actual value
    """
    base_path = ["configuration"]
    base_path.extend(path)
    samples = TimeoutSampler(
        wait_timeout=timeout,
        sleep=1,
        func=lambda: benedict(
            get_kubevirt_hyperconverged_spec(
                admin_client=admin_client, hco_namespace=hco_namespace
            ),
            keypath_separator=None,
        ).get(base_path),
    )
    try:
        for sample in samples:
            if sample and sample == value:
                break
    except TimeoutExpiredError:
        hco_annotations = get_hyperconverged_resource(
            client=admin_client, hco_ns_name=hco_namespace.name
        ).instance.metadata.annotations
        LOGGER.error(
            f"KV CR is not updated, path: {path}, expected value: {value}, HCO annotations: {hco_annotations}"
        )
        raise


def verify_pods_priority_class_value(pods, expected_value):
    failed_pods_list = [
        pod.name
        for pod in pods
        if pod.instance.spec["priorityClassName"] != expected_value
    ]
    assert (
        not failed_pods_list
    ), f"priorityClassName not set correctly in pods: {failed_pods_list}, should be {expected_value}"
