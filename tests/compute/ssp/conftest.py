import pytest


@pytest.fixture(scope="module")
def smbios_from_kubevirt_config(kubevirt_config_scope_module):
    """Extract SMBIOS default from kubevirt CR."""
    return kubevirt_config_scope_module["smbios"]


@pytest.fixture(scope="module")
def machine_type_from_kubevirt_config(kubevirt_config_scope_module):
    """Extract machine type default from kubevirt CR."""
    return kubevirt_config_scope_module["machineType"]
