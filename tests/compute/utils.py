# -*- coding: utf-8 -*-
import logging

from utilities.virt import (
    execute_winrm_cmd,
    vm_console_run_commands,
    wait_for_vm_interfaces,
)


LOGGER = logging.getLogger(__name__)


def vm_started(vm, wait_for_interfaces=True):
    """Start a VM and wait for its status to be 'Running'

    If wait_for_interfaces - wait for interfaces to be up.
    """

    vm.start(wait=True)
    vm.vmi.wait_until_running()
    if wait_for_interfaces:
        wait_for_vm_interfaces(vmi=vm.vmi)


def remove_eth0_default_gw(vm, console_impl):
    vm_console_run_commands(
        console_impl=console_impl,
        vm=vm,
        commands=["sudo route del default gw 0.0.0.0 eth0"],
    )


def start_and_fetch_processid_on_windows_vm(
    vm, winrmcli_pod, process_name, helper_vm=False
):
    """ Start a process and fetch processid from the Windows VM """

    execute_winrm_cmd(
        vmi_ip=vm.vmi.virt_launcher_pod.instance.status.podIP,
        winrmcli_pod=winrmcli_pod,
        cmd=f"wmic process call create {process_name}",
        target_vm=vm,
        helper_vm=helper_vm,
    )
    return fetch_processid_from_windows_vm(
        vm=vm, winrmcli_pod=winrmcli_pod, process_name=process_name, helper_vm=helper_vm
    )


def fetch_processid_from_windows_vm(vm, winrmcli_pod, process_name, helper_vm=False):
    """ Fetch the processid from the Windows VM  """

    return execute_winrm_cmd(
        vmi_ip=vm.vmi.virt_launcher_pod.instance.status.podIP,
        winrmcli_pod=winrmcli_pod,
        cmd=f"wmic process where (Name='{process_name}') get processid /value",
        target_vm=vm,
        helper_vm=helper_vm,
    )
