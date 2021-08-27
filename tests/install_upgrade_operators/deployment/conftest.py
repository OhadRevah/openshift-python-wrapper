import pytest

from tests.install_upgrade_operators.utils import get_deployment_by_name


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
