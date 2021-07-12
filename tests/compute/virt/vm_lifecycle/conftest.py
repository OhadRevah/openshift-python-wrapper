from contextlib import contextmanager

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.template import Template
from ocp_resources.virtual_machine import VirtualMachine
from pytest_testconfig import py_config

from utilities.constants import TIMEOUT_30MIN
from utilities.infra import get_admin_client
from utilities.storage import create_dv, get_images_server_url
from utilities.virt import (
    VirtualMachineForTests,
    VirtualMachineForTestsFromTemplate,
    fedora_vm_body,
    running_vm,
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
    ) as vm:
        # Run the VM to enable SSH
        running_vm(vm=vm)
        yield vm


@contextmanager
def data_volume_vm(unprivileged_client, namespace):
    with create_dv(
        client=get_admin_client(),
        dv_name=py_config["latest_fedora_os_dict"]["template_labels"]["os"],
        namespace=py_config["golden_images_namespace"],
        url=f"{get_images_server_url(schema='http')}{py_config['latest_fedora_os_dict']['image_path']}",
        storage_class=py_config["default_storage_class"],
        access_modes=py_config["default_access_mode"],
        volume_mode=py_config["default_volume_mode"],
        size=py_config["latest_fedora_os_dict"]["dv_size"],
    ) as dv:
        # wait for dv import to start and complete
        dv.wait_for_status(status=DataVolume.Status.SUCCEEDED, timeout=TIMEOUT_30MIN)

        with VirtualMachineForTestsFromTemplate(
            name="fedora-vm-lifecycle",
            namespace=namespace.name,
            client=unprivileged_client,
            labels=Template.generate_template_labels(
                **py_config["latest_fedora_os_dict"]["template_labels"]
            ),
            data_volume=dv,
            run_strategy=default_run_strategy,
            termination_grace_period=0,
        ) as vm:
            # Run the VM to enable SSH
            running_vm(vm=vm)
            yield vm


@pytest.fixture(scope="module")
def lifecycle_vm(
    cluster_cpu_model_scope_module,
    unprivileged_client,
    namespace,
    vm_volumes_matrix__module__,
):
    """Wrapper fixture to generate the desired VM
    vm_volumes_matrix returns a string.
    globals() is used to call the actual contextmanager with that name
    request should be True to start vm and wait for interfaces, else False
    """
    with globals()[vm_volumes_matrix__module__](
        unprivileged_client=unprivileged_client,
        namespace=namespace,
    ) as vm:
        yield vm
