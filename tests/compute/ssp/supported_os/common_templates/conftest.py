# -*- coding: utf-8 -*-

import logging

import pytest
from utilities.virt import vm_console_run_commands

from .utils import activate_windows_online, add_windows_license, is_windows_activated


LOGGER = logging.getLogger(__name__)


def enabled_ssh_service_in_vm(request, vm_object_from_template):
    """ Enable SSH in VM using console

    The call to this function is triggered by calling either
    enabled_ssh_service_in_vm_scope_function or
    enabled_ssh_service_in_vm_scope_class.
    """

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
        console_impl=request.param["console_impl"],
        vm=vm_object_from_template,
        commands=commands,
    )


@pytest.fixture()
def enabled_ssh_service_in_vm_scope_function(
    request, vm_instance_from_template_scope_function
):
    enabled_ssh_service_in_vm(request, vm_instance_from_template_scope_function)


@pytest.fixture(scope="class")
def enabled_ssh_service_in_vm_scope_class(request, vm_object_from_template_scope_class):
    enabled_ssh_service_in_vm(request, vm_object_from_template_scope_class)


def vm_ssh_service(vm_object_from_template):
    """ Manages (creation and deletion) of a service to enable SSH access to the VM

    The call to this function is triggered by calling either
    vm_ssh_service_scope_function or
    vm_ssh_service_scope_class.
    """

    vm_object_from_template.ssh_enable()
    yield
    vm_object_from_template.ssh_service.delete(wait=True)


@pytest.fixture()
def vm_ssh_service_scope_function(vm_instance_from_template_scope_function):
    yield from vm_ssh_service(vm_instance_from_template_scope_function)


@pytest.fixture(scope="class")
def vm_ssh_service_scope_class(vm_object_from_template_scope_class):
    yield from vm_ssh_service(vm_object_from_template_scope_class)


@pytest.fixture()
def exposed_vm_service(request, vm_instance_from_template_scope_function):
    vm_instance_from_template_scope_function.custom_service_enable(
        service_name=request.param["service_name"], port=request.param["service_port"]
    )


@pytest.fixture(scope="class")
def activated_vm(
    request, vm_object_from_template_scope_class, winrmcli_pod_scope_class
):

    add_windows_license(
        vm_object_from_template_scope_class,
        winrmcli_pod_scope_class,
        windows_license=request.param["license_key"],
    )
    activate_windows_online(
        vm_object_from_template_scope_class, winrmcli_pod_scope_class,
    )
    assert is_windows_activated(
        vm_object_from_template_scope_class, winrmcli_pod_scope_class
    ), "VM license is not activated."
