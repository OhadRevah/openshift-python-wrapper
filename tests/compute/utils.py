# -*- coding: utf-8 -*-
import logging
import shlex

from ocp_resources.resource import TIMEOUT

from utilities.infra import run_ssh_commands
from utilities.virt import wait_for_ssh_connectivity, wait_for_vm_interfaces


LOGGER = logging.getLogger(__name__)
OS_PROC_NAME = {"linux": "ping", "windows": "mspaint.exe"}


def vm_started(vm, wait_for_interfaces=True):
    """Start a VM and wait for its status to be 'Running'

    If wait_for_interfaces - wait for interfaces to be up.
    """

    timeout = TIMEOUT
    # For VMs from common templates
    if vm.is_vm_from_template:
        # Windows 10 takes longer to start
        timeout = 2600 if "windows10" in vm.labels["vm.kubevirt.io/template"] else 2100

    vm.start(wait=True, timeout=timeout)
    vm.vmi.wait_until_running()
    if wait_for_interfaces:
        wait_for_vm_interfaces(vmi=vm.vmi)


def remove_eth0_default_gw(vm):
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split("sudo route del default gw 0.0.0.0 eth0"),
    )


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


def validate_pause_unpause_windows_vm(vm, pre_pause_pid=None):
    proc_name = OS_PROC_NAME["windows"]
    if not pre_pause_pid or not pre_pause_pid.isnumeric():
        pre_pause_pid = start_and_fetch_processid_on_windows_vm(
            vm=vm, process_name=proc_name
        )
    vm.vmi.pause(wait=True)
    vm.vmi.unpause(wait=True)
    wait_for_ssh_connectivity(vm=vm)
    post_pause_pid = fetch_processid_from_windows_vm(vm=vm, process_name=proc_name)
    kill_processes_by_name_windows(vm=vm, process_name=proc_name)
    assert (
        post_pause_pid == pre_pause_pid
    ), f"PID mismatch!\nPre pause PID is: {pre_pause_pid}\nPost pause PID is: {post_pause_pid}"


def start_and_fetch_processid_on_linux_vm(vm, process_name, args=""):
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split(f"{process_name} {args} </dev/null &>/dev/null &"),
    )
    return fetch_processid_from_linux_vm(vm=vm, process_name=process_name)


def fetch_processid_from_linux_vm(vm, process_name):
    return run_ssh_commands(host=vm.ssh_exec, commands=["pidof", process_name])[0]


def validate_pause_unpause_linux_vm(vm, pre_pause_pid=None):
    proc_name = OS_PROC_NAME["linux"]
    if not pre_pause_pid or not pre_pause_pid.isnumeric():
        pre_pause_pid = start_and_fetch_processid_on_linux_vm(
            vm=vm, process_name=proc_name, args="localhost"
        )
    vm.vmi.pause(wait=True)
    vm.vmi.unpause(wait=True)
    wait_for_ssh_connectivity(vm=vm)
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
