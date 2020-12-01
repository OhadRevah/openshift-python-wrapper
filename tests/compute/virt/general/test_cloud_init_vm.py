"""
Test VM with cloudInit disk.
"""

import pytest

from utilities import console
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    vm_console_run_commands,
    wait_for_console,
)


@pytest.fixture(
    params=[
        pytest.param(
            {"cloud_init_type": "cloudInitNoCloud"},
            marks=(pytest.mark.polarion("CNV-3804")),
            id="case: cloudInitNoCloud",
        ),
        pytest.param(
            {"cloud_init_type": "cloudInitConfigDrive"},
            marks=(pytest.mark.polarion("CNV-3805")),
            id="case: cloudInitConfigDrive",
        ),
    ]
)
def vm_with_cloud_init_type(request, namespace):
    """VM with cloudInit disk."""
    cloud_init_type = request.param["cloud_init_type"]
    name = f"vm-cloud-init-test-{cloud_init_type}".lower()
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
        cloud_init_type=cloud_init_type,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


def test_cloud_init_types(vm_with_cloud_init_type):
    wait_for_console(vm=vm_with_cloud_init_type, console_impl=console.Fedora)
    vm_console_run_commands(
        console_impl=console.Fedora,
        vm=vm_with_cloud_init_type,
        commands=["cat /etc/os-release"],
    )
