import pytest
import yaml


@pytest.fixture(scope="module")
def smbios_from_kubevirt_config_cm(kubevirt_config_cm):
    """ Extract SMBIOS default from kubevirt config map. """
    return yaml.safe_load(kubevirt_config_cm.instance.data.smbios)


@pytest.fixture(scope="module")
def machine_type_from_kubevirt_config_cm(kubevirt_config_cm):
    """ Extract machine type default from kubevirt config map. """
    return kubevirt_config_cm.instance.data["machine-type"]
