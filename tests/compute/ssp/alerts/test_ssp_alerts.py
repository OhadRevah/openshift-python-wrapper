import pytest
from ocp_resources.deployment import Deployment

from tests.compute.utils import verify_no_listed_alerts_on_cluster
from utilities.constants import SSP_OPERATOR, VIRT_TEMPLATE_VALIDATOR
from utilities.infra import get_pod_by_name_prefix, update_custom_resource


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


def verify_ssp_pod_is_running(dyn_client, hco_namespace):
    pod = get_pod_by_name_prefix(
        dyn_client=dyn_client,
        pod_prefix=SSP_OPERATOR,
        namespace=hco_namespace.name,
    )
    pod.wait_for_status(status=pod.Status.RUNNING)


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


@pytest.fixture()
def template_validator_finalizer(hco_namespace):
    deployment = Deployment(name=VIRT_TEMPLATE_VALIDATOR, namespace=hco_namespace.name)
    with update_custom_resource(
        patch={
            deployment: {
                "metadata": {"finalizers": ["ssp.kubernetes.io/temporary-finalizer"]}
            }
        }
    ):
        yield


@pytest.fixture()
def deleted_ssp_operator_pod(admin_client, hco_namespace):
    get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix=SSP_OPERATOR,
        namespace=hco_namespace.name,
    ).delete(wait=True)
    yield
    verify_ssp_pod_is_running(dyn_client=admin_client, hco_namespace=hco_namespace)


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

    @pytest.mark.order(after="test_no_ssp_alerts_on_healthy_cluster")
    @pytest.mark.parametrize(
        "alert_not_firing_before_running_test",
        [
            pytest.param(
                SSP_FAILING_TO_RECONCILE,
                marks=pytest.mark.polarion("CNV-7711"),
            ),
        ],
        indirect=True,
    )
    def test_alert_ssp_failing_to_reconcile(
        self,
        prometheus,
        alert_not_firing_before_running_test,
        paused_ssp_operator,
        template_validator_finalizer,
        deleted_ssp_operator_pod,
    ):
        prometheus.alert_sampler(alert=alert_not_firing_before_running_test)
