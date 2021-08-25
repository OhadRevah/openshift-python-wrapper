import pytest
from ocp_resources.resource import Resource


virt_label_dict = {
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
