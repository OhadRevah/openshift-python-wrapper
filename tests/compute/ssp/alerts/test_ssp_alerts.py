import pytest

from tests.compute.utils import verify_no_listed_alerts_on_cluster
from utilities.constants import SSP_OPERATOR, VIRT_TEMPLATE_VALIDATOR
from utilities.infra import update_custom_resource


SSP_DOWN = "SSPDown"
SSP_TEMPLATE_VALIDATOR_DOWN = "SSPTemplateValidatorDown"
SSP_COMMON_TEMPLATES_MODIFICATION_REVERTED = "SSPCommonTemplatesModificationReverted"
SSP_HIGH_RATE_REJECTED_VMS = "SSPHighRateRejectedVms"
SSP_FAILING_TO_RECONCILE = "SSPFailingToReconcile"

SSP_ALERTS_LIST = [
    SSP_DOWN,
    SSP_TEMPLATE_VALIDATOR_DOWN,
    SSP_COMMON_TEMPLATES_MODIFICATION_REVERTED,
    SSP_HIGH_RATE_REJECTED_VMS,
    SSP_FAILING_TO_RECONCILE,
]


@pytest.fixture()
def paused_ssp_operator(hco_namespace, ssp_cr):
    """
    Pause ssp-operator to avoid from reconciling any related objects
    """
    with update_custom_resource(
        patch={
            ssp_cr: {
                "metadata": {"annotations": {"kubevirt.io/operator.paused": "true"}}
            }
        }
    ):
        yield


@pytest.fixture()
def alert_not_firing_before_running_test(prometheus, request):
    alert = request.param
    if prometheus.get_alert(alert):
        pytest.xfail(
            f"Alert {alert} should not be in Firing or in Pending state on a cluster before running test"
        )
    return alert


class TestSSPAlerts:
    @pytest.mark.polarion("CNV-7612")
    def test_no_ssp_alerts_on_healthy_cluster(
        self,
        prometheus,
    ):
        verify_no_listed_alerts_on_cluster(
            prometheus=prometheus, alerts_list=SSP_ALERTS_LIST
        )

    @pytest.mark.order(after="test_no_ssp_alerts_on_healthy_cluster")
    @pytest.mark.parametrize(
        "scaled_deployment, alert_not_firing_before_running_test",
        [
            pytest.param(
                {"deployment_name": VIRT_TEMPLATE_VALIDATOR, "replicas": 0},
                SSP_TEMPLATE_VALIDATOR_DOWN,
                marks=pytest.mark.polarion("CNV-7615"),
            ),
            pytest.param(
                {"deployment_name": SSP_OPERATOR, "replicas": 0},
                SSP_DOWN,
                marks=pytest.mark.polarion("CNV-7614"),
            ),
        ],
        indirect=True,
    )
    def test_alert_ssp_pods_down(
        self,
        prometheus,
        alert_not_firing_before_running_test,
        paused_ssp_operator,
        scaled_deployment,
    ):
        prometheus.alert_sampler(alert=alert_not_firing_before_running_test)
