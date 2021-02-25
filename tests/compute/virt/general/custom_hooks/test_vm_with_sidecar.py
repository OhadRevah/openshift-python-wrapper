"""
VM with sidecar
"""

import shlex

import pytest

from utilities.infra import BUG_STATUS_CLOSED, run_ssh_commands
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    running_vm,
)


pytestmark = pytest.mark.bugzilla(
    1904132, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)


class FedoraVirtualMachineWithSideCar(VirtualMachineForTests):
    def __init__(self, name, namespace, interfaces=None, networks=None, client=None):
        super().__init__(
            name=name,
            namespace=namespace,
            interfaces=interfaces,
            networks=networks,
            client=client,
            cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
        )

    def to_dict(self):
        self.body = fedora_vm_body(name=self.name)
        res = super().to_dict()

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
def sidecar_vm(namespace, unprivileged_client):
    """ Test VM with sidecar hook """
    name = "vmi-with-sidecar-hook"
    with FedoraVirtualMachineWithSideCar(
        name=name, namespace=namespace.name, client=unprivileged_client
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.mark.polarion("CNV-840")
def test_vm_with_sidecar_hook(sidecar_vm):
    """
    Test VM with sidecar hook, Install dmidecode with annotation
    smbios.vm.kubevirt.io/baseBoardManufacturer: "Radical Edward"
    And check that package includes manufacturer: "Radical Edward"
    """
    run_ssh_commands(
        host=sidecar_vm.ssh_exec,
        commands=shlex.split(
            "sudo dmidecode -s baseboard-manufacturer | grep 'Radical Edward'\n"
        ),
    )
