import pytest
from pytest_testconfig import py_config


@pytest.fixture(scope="session")
def cnv_source(pytestconfig):
    return pytestconfig.option.cnv_source


@pytest.fixture(scope="session")
def cnv_registry_source(cnv_source):
    return py_config["cnv_registry_sources"][cnv_source]


@pytest.fixture(scope="session")
def cnv_version(pytestconfig):
    return pytestconfig.option.cnv_version


@pytest.fixture(scope="session")
def hco_version(cnv_version):
    return f"kubevirt-hyperconverged-operator.v{cnv_version}"


@pytest.fixture(scope="module")
def is_cnv_deployment(pytestconfig):
    """ Returns True if requested upgrade or install is for CNV else False """
    return cnv_upgrade or pytestconfig.getoption("install_cnv")


@pytest.fixture()
def is_deployment_from_production_source(is_cnv_deployment, cnv_source):
    return is_cnv_deployment and cnv_source == "production"


@pytest.fixture(scope="session")
def cnv_upgrade(pytestconfig):
    """ Returns True if requested upgrade if for CNV else False """
    return pytestconfig.option.upgrade == "cnv"
