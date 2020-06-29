# -*- coding: utf-8 -*-
import logging

from utilities.virt import vm_console_run_commands, wait_for_vm_interfaces


LOGGER = logging.getLogger(__name__)


def vm_started(vm, wait_for_interfaces=True):
    """ Start a VM and wait for its status to be 'Running'

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
