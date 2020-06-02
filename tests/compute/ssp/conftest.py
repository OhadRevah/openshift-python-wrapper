import pytest
import yaml
from pytest_testconfig import config as py_config
from resources.configmap import ConfigMap


@pytest.fixture(scope="module")
def get_kubevirt_config_cm():
    return ConfigMap(name="kubevirt-config", namespace=py_config["hco_namespace"])


@pytest.fixture(scope="module")
def smbios_from_kubevirt_config_cm(get_kubevirt_config_cm):
    """ Extract SMBIOS default from kubevirt config map. """
    return yaml.load(get_kubevirt_config_cm.instance.data.smbios)


@pytest.fixture(scope="module")
def machine_type_from_kubevirt_config_cm(get_kubevirt_config_cm):
    """ Extract machine type default from kubevirt config map. """
    return get_kubevirt_config_cm.instance.data["machine-type"]
