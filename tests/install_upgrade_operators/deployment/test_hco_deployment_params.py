import pytest

from tests.install_upgrade_operators.deployment.utils import (
    validate_liveness_probe_fields,
    validate_request_fields,
)


pytestmark = pytest.mark.sno


@pytest.mark.parametrize(
    "deployment_by_name",
    [
        pytest.param(
            {"deployment_name": "hco-webhook"},
            marks=(pytest.mark.polarion("CNV-6500")),
            id="test-hco-webhook-liveness-probe",
        ),
        pytest.param(
            {"deployment_name": "hco-operator"},
            marks=(pytest.mark.polarion("CNV-6499")),
            id="test-hco-operator-liveness-probe",
        ),
    ],
    indirect=True,
)
def test_liveness_probe(deployment_by_name):
    """Validates various livenessProbe fields values for different deployment objects"""
    validate_liveness_probe_fields(deployment=deployment_by_name)


@pytest.mark.parametrize(
    "deployment_by_name, cpu_min_value",
    [
        pytest.param(
            {"deployment_name": "hco-webhook"},
            5,
            marks=(pytest.mark.polarion("CNV-7187")),
            id="test-hco-webhook-req-param",
        ),
        pytest.param(
            {"deployment_name": "hco-operator"},
            5,
            marks=(pytest.mark.polarion("CNV-7188")),
            id="test-hco-operator-req-param",
        ),
    ],
    indirect=["deployment_by_name"],
)
def test_request_param(deployment_by_name, cpu_min_value):
    """Validates resources.requests fields keys and default cpu values for different deployment objects"""
    validate_request_fields(deployment=deployment_by_name, cpu_min_value=cpu_min_value)
