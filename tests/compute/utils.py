# -*- coding: utf-8 -*-
import logging
import shlex

import rrmngmnt
from resources.resource import TIMEOUT
from resources.virtual_machine import VirtualMachineInstanceMigration

from utilities.virt import vm_console_run_commands, wait_for_vm_interfaces


LOGGER = logging.getLogger(__name__)


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


def remove_eth0_default_gw(vm, console_impl):
    vm_console_run_commands(
        console_impl=console_impl,
        vm=vm,
        commands=["sudo route del default gw 0.0.0.0 eth0"],
    )


def start_and_fetch_processid_on_windows_vm(vm, process_name):
    """ Start a process and fetch processid from the Windows VM """

    vm.ssh_exec.run_command(
        command=shlex.split(f"wmic process call create {process_name}")
    )
    return fetch_processid_from_windows_vm(vm=vm, process_name=process_name)


def fetch_processid_from_windows_vm(vm, process_name):
    """ Fetch the processid from the Windows VM  """

    cmd = shlex.split(
        fr"wmic process where (Name=\'{process_name}\') get processid /value"
    )
    return vm.ssh_exec.run_command(command=cmd)[1]


def migrate_vm(vm, timeout=1500):
    with VirtualMachineInstanceMigration(
        name=vm.name,
        namespace=vm.namespace,
        vmi=vm.vmi,
    ) as mig:
        mig.wait_for_status(status=mig.Status.SUCCEEDED, timeout=timeout)


def rrmngmnt_host(usr, passwd, ip, port):
    host = rrmngmnt.Host(ip=str(ip))
    host_user = rrmngmnt.user.User(name=usr, password=passwd)
    host._set_executor_user(user=host_user)
    host.executor_factory = rrmngmnt.ssh.RemoteExecutorFactory(port=port)
    return host
