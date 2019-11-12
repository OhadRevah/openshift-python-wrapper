# -*- coding: utf-8 -*-

import logging

import pytest
from utilities import console
from utilities.virt import vm_console_run_commands


LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def enabled_ssh_service_in_vm(vm_object_from_template):
    """ Enable SSH in VM using console """

    LOGGER.info("Enable SSH in VM.")

    commands = [
        r"sudo sed -iE "
        r"'s/^#\?PasswordAuthentication no/PasswordAuthentication yes/g'"
        r" /etc/ssh/sshd_config",
        "",
        "sudo systemctl enable sshd",
        "sudo systemctl restart sshd",
    ]

    vm_console_run_commands(
        console_impl=console.RHEL, vm=vm_object_from_template, commands=commands
    )


@pytest.fixture()
def vm_ssh_service(vm_object_from_template):
    """ Manages (creation and deletion) of a service to enable SSH access to the VM """

    vm_object_from_template.ssh_enable()
    yield
    vm_object_from_template.ssh_service.delete(wait=True)
