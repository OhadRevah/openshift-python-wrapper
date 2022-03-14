import pytest
from pytest_testconfig import py_config

from tests.install_upgrade_operators.utils import (
    get_network_addon_config,
    wait_for_stabilize,
)
from utilities.infra import update_custom_resource
from utilities.storage import get_hyperconverged_cdi
from utilities.virt import get_hyperconverged_kubevirt


@pytest.fixture(scope="session")
def cnv_source(pytestconfig):
    return pytestconfig.option.cnv_source


@pytest.fixture(scope="session")
def cnv_registry_source(cnv_source):
    return py_config["cnv_registry_sources"][cnv_source]


@pytest.fixture(scope="session")
def hco_current_version(cnv_current_version):
    return f"kubevirt-hyperconverged-operator.v{cnv_current_version}"


@pytest.fixture()
def is_deployment_from_production_source(cnv_source):
    return cnv_source == "production"


@pytest.fixture()
def is_deployment_from_stage_source(cnv_source):
    return cnv_source == "stage"


@pytest.fixture()
def kubevirt_resource(admin_client, hco_namespace):
    return get_hyperconverged_kubevirt(
        admin_client=admin_client, hco_namespace=hco_namespace
    )


@pytest.fixture()
def cdi_resource(admin_client):
    return get_hyperconverged_cdi(admin_client=admin_client)


@pytest.fixture()
def cnao_resource(admin_client):
    return get_network_addon_config(admin_client=admin_client)


@pytest.fixture()
def cnao_spec(cnao_resource):
    return cnao_resource.instance.to_dict()["spec"]


@pytest.fixture()
def updated_hco_cr(
    request, hyperconverged_resource_scope_function, admin_client, hco_namespace
):
    """
    This fixture updates HCO CR with values specified via request.param

    Args:
        hyperconverged_resource_scope_function (HyperConverged): HCO CR

    """
    with update_custom_resource(
        patch={hyperconverged_resource_scope_function: request.param["patch"]},
    ):
        yield
    wait_for_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture()
def updated_kubevirt_cr(request, kubevirt_resource, admin_client, hco_namespace):
    """
    Attempts to update kubevirt CR
    """
    with update_custom_resource(
        patch={kubevirt_resource: request.param["patch"]},
    ):
        yield
    wait_for_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture()
def ssp_cr_spec(ssp_resource_scope_function):
    return ssp_resource_scope_function.instance.to_dict()["spec"]
