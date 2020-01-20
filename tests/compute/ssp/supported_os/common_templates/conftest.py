# -*- coding: utf-8 -*-

import logging

import pytest

from .utils import wait_for_windows_vm


LOGGER = logging.getLogger(__name__)


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


@pytest.fixture()
def started_windows_vm(
    request, vm_instance_from_template_scope_function, winrmcli_pod_scope_function
):
    wait_for_windows_vm(
        vm=vm_instance_from_template_scope_function,
        version=request.param["os_version"],
        winrmcli_pod=winrmcli_pod_scope_function,
        timeout=1800,
    )
