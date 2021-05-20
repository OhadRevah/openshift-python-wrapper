"""
Test SMBIOS values from kubevirt config are:
1. Populated correctly (according to CNV version)
2. Set in VM
"""

import pytest

from tests.compute.ssp import utils as ssp_utils
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


pytestmark = pytest.mark.post_upgrade


@pytest.fixture()
def configmap_smbios_vm(unprivileged_client, namespace):
    name = "configmap-smbios-vm"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def smbios_defaults(admin_client, cnv_current_version):
    smbios_defaults = {
        "family": "Red Hat",
        "product": "Container-native virtualization",
        "manufacturer": "Red Hat",
        "sku": cnv_current_version,
        "version": cnv_current_version,
    }
    return smbios_defaults


@pytest.mark.polarion("CNV-4346")
def test_cm_smbios_defaults(
    skip_upstream, smbios_from_kubevirt_config, smbios_defaults
):
    ssp_utils.check_smbios_defaults(
        smbios_defaults=smbios_defaults, cm_values=smbios_from_kubevirt_config
    )


@pytest.mark.polarion("CNV-4325")
def test_vm_smbios_default_values(
    skip_upstream,
    smbios_from_kubevirt_config,
    configmap_smbios_vm,
):
    ssp_utils.check_vm_xml_smbios(
        vm=configmap_smbios_vm,
        cm_values=smbios_from_kubevirt_config,
    )
