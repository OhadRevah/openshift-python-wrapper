import pytest
from ocp_resources.resource import Resource

from utilities.infra import BUG_STATUS_CLOSED


pytestmark = pytest.mark.sno


virt_label_dict = {
    "virt-api": f"{Resource.ApiGroup.KUBEVIRT_IO}=virt-api",
    "virt-handler": f"{Resource.ApiGroup.KUBEVIRT_IO}=virt-handler",
    "virt-operator": f"{Resource.ApiGroup.KUBEVIRT_IO}=virt-operator",
    "virt-controller": f"{Resource.ApiGroup.KUBEVIRT_IO}=virt-controller ",
}


@pytest.mark.parametrize(
    "virt_pod_info_from_prometheus, virt_pod_names_by_label",
    [
        pytest.param(
            "kubevirt_virt_controller_ready",
            virt_label_dict["virt-controller"],
            marks=pytest.mark.polarion("CNV-7110"),
            id="kubevirt_virt_controller_ready",
        ),
        pytest.param(
            "kubevirt_virt_operator_ready",
            virt_label_dict["virt-operator"],
            marks=pytest.mark.polarion("CNV-7111"),
            id="kubevirt_virt_operator_ready",
        ),
        pytest.param(
            "kubevirt_virt_operator_leading",
            virt_label_dict["virt-operator"],
            marks=pytest.mark.polarion("CNV-7112"),
            id="kubevirt_virt_operator_leading",
        ),
        pytest.param(
            "kubevirt_virt_controller_leading",
            virt_label_dict["virt-controller"],
            marks=pytest.mark.polarion("CNV-7113"),
            id="kubevirt_virt_controller_leading",
        ),
    ],
    indirect=True,
)
def test_virt_recording_rules(
    prometheus,
    admin_client,
    hco_namespace,
    virt_pod_info_from_prometheus,
    virt_pod_names_by_label,
):
    """
    This test will check that recording rules for 'virt-operator and virt-controller'
    showing the pod information in the output.
    """
    # Check Pod names.
    assert (
        set(virt_pod_names_by_label) == virt_pod_info_from_prometheus
    ), f"Actual pods {virt_pod_names_by_label} not matching with expected pods {virt_pod_info_from_prometheus}"


@pytest.mark.bugzilla(
    2008166, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)
@pytest.mark.parametrize(
    "virt_up_metrics_values, virt_pod_names_by_label",
    [
        pytest.param(
            "kubevirt_virt_api_up_total",
            virt_label_dict["virt-api"],
            marks=pytest.mark.polarion("CNV-7106"),
            id="kubevirt_virt_api_up_total",
        ),
        pytest.param(
            "kubevirt_virt_operator_up_total",
            virt_label_dict["virt-operator"],
            marks=pytest.mark.polarion("CNV-7107"),
            id="kubevirt_virt_operator_up_total",
        ),
        pytest.param(
            "kubevirt_virt_handler_up_total",
            virt_label_dict["virt-handler"],
            marks=pytest.mark.polarion("CNV-7108"),
            id="kubevirt_virt_handler_up_total",
        ),
        pytest.param(
            "kubevirt_virt_controller_up_total",
            virt_label_dict["virt-controller"],
            marks=pytest.mark.polarion("CNV-7109"),
            id="kubevirt_virt_controller_up_total",
        ),
    ],
    indirect=True,
)
def test_virt_up_recording_rules(
    prometheus,
    admin_client,
    hco_namespace,
    virt_up_metrics_values,
    virt_pod_names_by_label,
):
    """
    This test will check that 'up' recording rules for 'virt_api',
    'virt_controller','virt_operator', 'virt_handler' showing 'sum()' of pods in the output.
    More details on 'up': https://help.sumologic.com/Metrics/Kubernetes_Metrics#up-metrics

    Example:
        For 2 virt-api pods, 'kubevirt_virt_api_up_total' recording rule show 2 as output.
    """
    # Check values from Prometheus and acutal Pods.
    assert (
        len(virt_pod_names_by_label) == virt_up_metrics_values
    ), f"Actual pod count {virt_pod_names_by_label} not matching with expected pod count {virt_up_metrics_values}"
