import pytest

from tests.install_upgrade_operators.utils import get_deployment_by_name
from utilities.constants import HPP_POOL
from utilities.infra import get_deployments


@pytest.fixture()
def deployment_by_name(request, admin_client, hco_namespace):
    """
    Gets a deployment object by name.
    """
    deployment_name = request.param["deployment_name"]
    deployment_by_name = get_deployment_by_name(
        deployment_name=deployment_name,
        admin_client=admin_client,
        namespace_name=hco_namespace.name,
    )
    assert deployment_by_name.exists, f"Deployment {deployment_name} not found."
    yield deployment_by_name


@pytest.fixture(scope="module")
def cnv_deployments(admin_client, hco_namespace):
    return [
        deployment
        for deployment in get_deployments(
            admin_client=admin_client, namespace=hco_namespace.name
        )
        if not deployment.name.startswith(HPP_POOL)
    ]
