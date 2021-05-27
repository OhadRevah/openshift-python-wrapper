import pytest
from pytest_testconfig import py_config

from tests.install_upgrade_operators.utils import (
    get_hyperconverged_cdi,
    get_hyperconverged_kubevirt,
)


@pytest.fixture(scope="session")
def cnv_source(pytestconfig):
    return pytestconfig.option.cnv_source


@pytest.fixture(scope="session")
def cnv_registry_source(cnv_source):
    return py_config["cnv_registry_sources"][cnv_source]


@pytest.fixture(scope="session")
def cnv_target_version(pytestconfig):
    return pytestconfig.option.cnv_version


@pytest.fixture(scope="session")
def hco_target_version(cnv_target_version):
    return f"kubevirt-hyperconverged-operator.v{cnv_target_version}"


@pytest.fixture(scope="session")
def hco_current_version(cnv_current_version):
    return f"kubevirt-hyperconverged-operator.v{cnv_current_version}"


@pytest.fixture(scope="module")
def is_cnv_deployment(pytestconfig):
    """Returns True if requested upgrade or install is for CNV else False"""
    return cnv_upgrade or pytestconfig.getoption("install_cnv")


@pytest.fixture()
def is_deployment_from_production_source(is_cnv_deployment, cnv_source):
    return is_cnv_deployment and cnv_source == "production"


@pytest.fixture()
def is_deployment_from_stage_source(is_cnv_deployment, cnv_source):
    return is_cnv_deployment and cnv_source == "stage"


@pytest.fixture(scope="session")
def cnv_upgrade(pytestconfig):
    """Returns True if requested upgrade if for CNV else False"""
    return pytestconfig.option.upgrade == "cnv"


@pytest.fixture()
def kubevirt_resource(admin_client, hco_namespace):
    return get_hyperconverged_kubevirt(
        admin_client=admin_client, hco_namespace=hco_namespace
    )


@pytest.fixture()
def cdi_resource(admin_client, hco_namespace):
    return get_hyperconverged_cdi(
        admin_client=admin_client, hco_namespace=hco_namespace
    )


@pytest.fixture()
def cdi_spec(cdi_resource):
    return cdi_resource.instance.to_dict()["spec"]
