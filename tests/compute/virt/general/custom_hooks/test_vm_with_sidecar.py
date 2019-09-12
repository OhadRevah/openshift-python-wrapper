"""
VM with sidecar
"""

import pytest

from tests import utils as test_utils
from tests.utils import VirtualMachineForTests
from utilities import console

CHECK_DMIDECODE_PACKAGE = (
    "sudo dmidecode -s baseboard-manufacturer | grep 'Radical Edward' | wc -l\n"
)


class FedoraVirtualMachineWithSideCar(VirtualMachineForTests):
    def __init__(self, name, namespace, interfaces=None, networks=None):
        super().__init__(
            name=name, namespace=namespace, interfaces=interfaces, networks=networks
        )

    def _to_dict(self):
        res = super()._to_dict()

        res["spec"]["template"]["metadata"].setdefault("annotations", {})
        res["spec"]["template"]["metadata"]["annotations"].update(
            {
                "hooks.kubevirt.io/hookSidecars": '[{"image": "kubevirt/example-hook-sidecar:v0.13.3"}]',
                "smbios.vm.kubevirt.io/baseBoardManufacturer": "Radical Edward",
            }
        )

        res["spec"]["template"]["metadata"].setdefault("labels", {})
        res["spec"]["template"]["metadata"]["labels"].update({"special": self.name})

        return res


@pytest.fixture()
def sidecar_vm(default_client, virt_namespace):
    name = "vmi-with-sidecar-hook"
    with FedoraVirtualMachineWithSideCar(
        name=name, namespace=virt_namespace.name
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.fixture()
def running_sidecar_vm(sidecar_vm):
    test_utils.wait_for_vm_interfaces(sidecar_vm.vmi)
    yield sidecar_vm


@pytest.mark.polarion("CNV-840")
def test_vm_with_sidecar_hook(running_sidecar_vm):
    """
    Test VM with sidecar hook, Install dmidecode with annotation
    smbios.vm.kubevirt.io/baseBoardManufacturer: "Radical Edward"
    And check that package includes manufacturer: "Radical Edward"
    """
    with console.Console(vm=running_sidecar_vm) as vm_console:
        vm_console.sendline(CHECK_DMIDECODE_PACKAGE)
        vm_console.expect("1", timeout=20)
