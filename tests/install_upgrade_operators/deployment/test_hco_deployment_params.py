import pytest

from tests.install_upgrade_operators.deployment.utils import (
    validate_liveness_probe_fields,
)
from tests.install_upgrade_operators.utils import get_deployment_by_name


@pytest.mark.parametrize(
    "deployment_name",
    [
        pytest.param(
            "hco-webhook",
            marks=(pytest.mark.polarion("CNV-6500")),
            id="test-hco-webhook",
        ),
        pytest.param(
            "hco-operator",
            marks=(pytest.mark.polarion("CNV-6499")),
            id="test-hco-operator",
        ),
    ],
)
def test_liveness_probe(deployment_name, admin_client, hco_namespace):
    """Validates various livenessProbe fields values for different deployment objects"""
    deployment = get_deployment_by_name(
        deployment_name=deployment_name,
        admin_client=admin_client,
        namespace_name=hco_namespace.name,
    )
    validate_liveness_probe_fields(deployment=deployment)
