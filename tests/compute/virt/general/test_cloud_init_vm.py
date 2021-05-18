"""
Test VM with cloudInit disk.
"""

import pytest

from utilities.constants import CLOUD_INIT_NO_CLOUD, CLOUND_INIT_CONFIG_DRIVE
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


pytestmark = pytest.mark.post_upgrade


@pytest.fixture(
    params=[
        pytest.param(
            {"cloud_init_type": CLOUD_INIT_NO_CLOUD},
            marks=(pytest.mark.polarion("CNV-3804")),
            id=f"case: {CLOUD_INIT_NO_CLOUD}",
        ),
        pytest.param(
            {"cloud_init_type": CLOUND_INIT_CONFIG_DRIVE},
            marks=(pytest.mark.polarion("CNV-3805")),
            id=f"case: {CLOUND_INIT_CONFIG_DRIVE}",
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
        cloud_init_type=cloud_init_type,
    ) as vm:
        running_vm(vm=vm)
        yield vm


def test_cloud_init_types(vm_with_cloud_init_type):
    vm_with_cloud_init_type.ssh_exec.executor().is_connective()
