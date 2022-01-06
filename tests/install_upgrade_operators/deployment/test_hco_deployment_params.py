import pytest

from tests.install_upgrade_operators.deployment.utils import (
    validate_cnv_deployments_priorty_class,
    validate_liveness_probe_fields,
    validate_request_fields,
)
from utilities.constants import HCO_OPERATOR, HCO_WEBHOOK


pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


@pytest.mark.parametrize(
    "deployment_by_name",
    [
        pytest.param(
            {"deployment_name": HCO_WEBHOOK},
            marks=(pytest.mark.polarion("CNV-6500")),
            id="test-hco-webhook-liveness-probe",
        ),
        pytest.param(
            {"deployment_name": HCO_OPERATOR},
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
            {"deployment_name": HCO_WEBHOOK},
            5,
            marks=(pytest.mark.polarion("CNV-7187")),
            id="test-hco-webhook-req-param",
        ),
        pytest.param(
            {"deployment_name": HCO_OPERATOR},
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


@pytest.mark.polarion("CNV-7675")
def test_cnv_deployment_priority_class_name(cnv_deployments):
    validate_cnv_deployments_priorty_class(cnv_deployments=cnv_deployments)
