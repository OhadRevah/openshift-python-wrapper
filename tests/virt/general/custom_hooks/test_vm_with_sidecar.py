"""
VM with sidecar
"""

import pytest

from tests import utils as test_utils
from tests.utils import FedoraVirtualMachine
from utilities import console

CHECK_DMIDECODE_PACKAGE = "sudo dmidecode -s baseboard-manufacturer | grep 'Radical Edward' | wc -l\n"

CLOUD_INIT_USER_DATA = r'''
    #cloud-config
    password: fedora
    chpasswd: { expire: False }
    bootcmd:
      - dnf install -y dmidecode qemu-guest-agent
    runcmd:
      - systemctl start qemu-guest-agent'''


class FedoraVirtualMachineWithSideCar(FedoraVirtualMachine):
    def __init__(
        self, name, namespace, interfaces=None, networks=None, cloud_init_user_data=None, **vm_attr
    ):
        super().__init__(
            name=name,
            namespace=namespace,
            interfaces=interfaces,
            networks=networks,
            cloud_init_user_data=cloud_init_user_data,
            **vm_attr
        )

    def _to_dict(self):
        res = super()._to_dict()
        res['spec']['template']['metadata'].update({
            "annotations": {
                "hooks.kubevirt.io/hookSidecars": '[{"image": "kubevirt/example-hook-sidecar:v0.13.3"}]',
                "smbios.vm.kubevirt.io/baseBoardManufacturer": "Radical Edward",
            },
            'labels': {'special': self.name},
        })

        return res


@pytest.fixture()
def sidecar_vm(default_client, virt_namespace):
    name = "vmi-with-sidecar-hook"
    with FedoraVirtualMachineWithSideCar(
        name=name, namespace=virt_namespace.name, cloud_init_user_data=CLOUD_INIT_USER_DATA
    ) as vm:
        assert vm.start(wait=True)
        yield vm


@pytest.fixture()
def running_sidecar_vm(sidecar_vm):
    test_utils.wait_for_vm_interfaces(sidecar_vm.vmi, timeout=720)
    yield sidecar_vm


@pytest.mark.polarion("CNV-840")
def test_vm_with_sidecar_hook(running_sidecar_vm, virt_namespace):
    """
    Test VM with sidecar hook, Install dmidecode with annotation
    smbios.vm.kubevirt.io/baseBoardManufacturer: "Radical Edward"
    And check that package includes manufacturer: "Radical Edward"
    """
    with console.Fedora(vm=running_sidecar_vm.name, namespace=virt_namespace.name) as vm_console:
        vm_console.sendline(CHECK_DMIDECODE_PACKAGE)
        vm_console.expect("1", timeout=20)
