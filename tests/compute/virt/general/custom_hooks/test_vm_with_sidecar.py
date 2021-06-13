"""
VM with sidecar
"""

import shlex

import pytest

from tests.compute.utils import update_hco_config, wait_for_updated_kv_value
from utilities.infra import run_ssh_commands
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


@pytest.fixture()
def enabled_sidecar_featuregate(
    hyperconverged_resource_scope_function,
    kubevirt_feature_gates,
    admin_client,
    hco_namespace,
):
    kubevirt_feature_gates.append("Sidecar")
    with update_hco_config(
        resource=hyperconverged_resource_scope_function,
        path="developerConfiguration/featureGates",
        value=kubevirt_feature_gates,
    ):
        wait_for_updated_kv_value(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            path=[
                "developerConfiguration",
                "featureGates",
            ],
            value=kubevirt_feature_gates,
        )
        yield


class FedoraVirtualMachineWithSideCar(VirtualMachineForTests):
    def __init__(self, name, namespace, interfaces=None, networks=None, client=None):
        super().__init__(
            name=name,
            namespace=namespace,
            interfaces=interfaces,
            networks=networks,
            client=client,
        )

    def to_dict(self):
        self.body = fedora_vm_body(name=self.name)
        res = super().to_dict()

        res["spec"]["template"]["metadata"].setdefault("annotations", {})
        res["spec"]["template"]["metadata"]["annotations"].update(
            {
                "hooks.kubevirt.io/hookSidecars": '[{"args": ["--version", "v1alpha2"], '
                '"image": "kubevirt/example-hook-sidecar:latest"}]',
                "smbios.vm.kubevirt.io/baseBoardManufacturer": "Radical Edward",
            }
        )

        res["spec"]["template"]["metadata"].setdefault("labels", {})
        res["spec"]["template"]["metadata"]["labels"].update({"special": self.name})

        return res


@pytest.fixture()
def sidecar_vm(namespace, unprivileged_client):
    """Test VM with sidecar hook"""
    name = "vmi-with-sidecar-hook"
    with FedoraVirtualMachineWithSideCar(
        name=name, namespace=namespace.name, client=unprivileged_client
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.mark.polarion("CNV-840")
def test_vm_with_sidecar_hook(enabled_sidecar_featuregate, sidecar_vm):
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
