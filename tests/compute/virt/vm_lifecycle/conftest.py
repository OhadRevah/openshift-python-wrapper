from contextlib import contextmanager

import pytest
from ocp_resources.template import Template
from ocp_resources.virtual_machine import VirtualMachine
from pytest_testconfig import py_config

from utilities.virt import (
    VirtualMachineForTests,
    VirtualMachineForTestsFromTemplate,
    fedora_vm_body,
)


default_run_strategy = VirtualMachine.RunStrategy.MANUAL


@contextmanager
def container_disk_vm(namespace, unprivileged_client, dv=None):
    """lifecycle_vm is used to call this fixture and data_volume_vm; dv is not needed in this use cases"""
    name = "fedora-vm-lifecycle"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
        run_strategy=default_run_strategy,
    ) as vm:
        yield vm


@contextmanager
def data_volume_vm(unprivileged_client, namespace, dv):
    with VirtualMachineForTestsFromTemplate(
        name="rhel-vm-lifecycle",
        namespace=namespace.name,
        client=unprivileged_client,
        labels=Template.generate_template_labels(
            **py_config["latest_rhel_os_dict"]["template_labels"]
        ),
        data_volume=dv,
        run_strategy=default_run_strategy,
    ) as vm:
        yield vm


@pytest.fixture(scope="module")
def lifecycle_vm(
    cluster_cpu_model_scope_module,
    unprivileged_client,
    namespace,
    vm_volumes_matrix__module__,
    golden_image_data_volume_scope_module,
):
    """Wrapper fixture to generate the desired VM
    vm_volumes_matrix returns a string.
    globals() is used to call the actual contextmanager with that name
    request should be True to start vm and wait for interfaces, else False
    """
    with globals()[vm_volumes_matrix__module__](
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        dv=golden_image_data_volume_scope_module,
    ) as vm:
        yield vm
