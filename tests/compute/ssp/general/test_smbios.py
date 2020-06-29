"""
Test SMBIOS values from kubevirt config are:
1. Populated correctly (according to CNV version)
2. Set in VM
"""

import pytest
from tests.compute.ssp import utils as ssp_utils
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


@pytest.fixture()
def configmap_smbios_vm(unprivileged_client, namespace):
    name = "configmap-smbios-vm"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        wait_for_vm_interfaces(vmi=vm.vmi)
        yield vm


@pytest.fixture()
def smbios_defaults(default_client, cnv_current_version):
    smbios_defaults = {
        "Family": "Red Hat",
        "Product": "Container-native virtualization",
        "Manufacturer": "Red Hat",
        "Sku": cnv_current_version,
        "Version": cnv_current_version,
    }
    return smbios_defaults


@pytest.mark.polarion("CNV-4346")
def test_cm_smbios_defaults(
    skip_upstream, smbios_from_kubevirt_config_cm, smbios_defaults
):
    ssp_utils.check_smbios_defaults(
        smbios_defaults=smbios_defaults, cm_values=smbios_from_kubevirt_config_cm
    )


@pytest.mark.polarion("CNV-4325")
def test_vm_smbios_default_values(
    skip_upstream, smbios_from_kubevirt_config_cm, configmap_smbios_vm,
):
    ssp_utils.check_vm_xml_smbios(
        vm=configmap_smbios_vm, cm_values=smbios_from_kubevirt_config_cm,
    )
