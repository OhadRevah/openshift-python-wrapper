"""
VM with sidecar
"""

import pytest

from tests import utils as test_utils
from utilities import console
from tests import config

CHECK_DMIDECODE_PACKAGE = "sudo dmidecode -s baseboard-manufacturer | grep 'Radical Edward' | wc -l\n"


@pytest.fixture()
def side_car_vm(default_client):
    name = "vmi-with-sidecar-hook"
    vm_params = {
        "metadata": {
            "annotations": {
                "hooks.kubevirt.io/hookSidecars": '[{"image": "kubevirt/example-hook-sidecar:v0.13.3"}]',
                "smbios.vm.kubevirt.io/baseBoardManufacturer": "Radical Edward",
            },
            'labels': {'special': name},
        },
        "cloud_init": {
            "bootcmd": ["dnf install -y dmidecode qemu-guest-agent"],
            "runcmd": ["systemctl start qemu-guest-agent"]
        }
    }
    vm = test_utils.create_vm_from_template(
        default_client=default_client, name="vmi-with-sidecar-hook",
        namespace=config.VIRT_NS, template=config.VM_YAML_FEDORA,
        template_params=config.VM_FEDORA_ATTRS, vm_params=vm_params,
    )
    assert vm.start(wait=True)
    yield vm
    vm.delete(wait=True)


@pytest.fixture()
def running_side_car_vm(side_car_vm):
    test_utils.wait_for_vm_interfaces(side_car_vm.vmi(), timeout=720)
    yield side_car_vm


def test_vm_with_sidecar_hook(running_side_car_vm):
    """
    Test VM with sidecar hook, Install dmidecode with annotation
    smbios.vm.kubevirt.io/baseBoardManufacturer: "Radical Edward"
    And check that package includes manufacturer: "Radical Edward"
    """
    with console.Fedora(vm=running_side_car_vm.name, namespace=config.VIRT_NS) as vm_console:
        vm_console.sendline(CHECK_DMIDECODE_PACKAGE)
        vm_console.expect("1", timeout=20)
