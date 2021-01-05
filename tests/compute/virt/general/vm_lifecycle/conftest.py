from contextlib import contextmanager

import pytest
from pytest_testconfig import py_config
from resources.datavolume import DataVolume
from resources.template import Template
from resources.virtual_machine import VirtualMachine

from utilities.storage import create_dv, get_images_external_http_server
from utilities.virt import (
    VirtualMachineForTests,
    VirtualMachineForTestsFromTemplate,
    fedora_vm_body,
)


default_run_strategy = VirtualMachine.RunStrategy.MANUAL


@contextmanager
def container_disk_vm(namespace, unprivileged_client):
    name = "fedora-vm-lifecycle"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
        run_strategy=default_run_strategy,
        ssh=True,
    ) as vm:
        yield vm


@contextmanager
def data_volume_vm(unprivileged_client, namespace):
    with create_dv(
        dv_name="fedora-dv-lifecycle",
        namespace=namespace.name,
        url=f"{get_images_external_http_server()}{py_config['latest_fedora_version']['image_path']}",
        storage_class=py_config["default_storage_class"],
        access_modes=py_config["default_access_mode"],
        volume_mode=py_config["default_volume_mode"],
        size=py_config["latest_fedora_version"]["dv_size"],
    ) as dv:
        # wait for dv import to start and complete
        dv.wait_for_status(status=DataVolume.Status.SUCCEEDED, timeout=1800)

        with VirtualMachineForTestsFromTemplate(
            name="fedora-vm-lifecycle",
            namespace=dv.namespace,
            client=unprivileged_client,
            labels=Template.generate_template_labels(
                **py_config["latest_fedora_version"]["template_labels"]
            ),
            data_volume=dv,
            run_strategy=default_run_strategy,
            ssh=True,
        ) as vm:
            yield vm


@pytest.fixture(scope="module")
def lifecycle_vm(unprivileged_client, namespace, vm_volumes_matrix__module__):
    """Wrapper fixture to generate the desired VM
    vm_volumes_matrix returns a string.
    globals() is used to call the actual contextmanager with that name
    request should be True to start vm and wait for interfaces, else False
    """
    with globals()[vm_volumes_matrix__module__](
        unprivileged_client=unprivileged_client, namespace=namespace
    ) as vm:
        yield vm
