import pytest

from tests.install_upgrade_operators.pod_validation.utils import (
    validate_cnv_pod_cpu_min_value,
    validate_cnv_pods_priority_class_name_exists,
    validate_cnv_pods_resource_request,
    validate_priority_class_value,
)
from utilities.constants import (
    BRIDGE_MARKER,
    CDI_APISERVER,
    CDI_DEPLOYMENT,
    CDI_OPERATOR,
    CDI_UPLOADPROXY,
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    HCO_OPERATOR,
    HCO_WEBHOOK,
    HOSTPATH_PROVISIONER,
    HOSTPATH_PROVISIONER_CSI,
    HOSTPATH_PROVISIONER_OPERATOR,
    HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD,
    KUBE_CNI_LINUX_BRIDGE_PLUGIN,
    KUBEMACPOOL_CERT_MANAGER,
    KUBEMACPOOL_MAC_CONTROLLER_MANAGER,
    NMSTATE_CERT_MANAGER,
    NMSTATE_HANDLER,
    NMSTATE_WEBHOOK,
    NODE_MAINTENANCE_OPERATOR,
    SSP_OPERATOR,
    VIRT_API,
    VIRT_CONTROLLER,
    VIRT_HANDLER,
    VIRT_OPERATOR,
    VIRT_TEMPLATE_VALIDATOR,
)
from utilities.infra import BUG_STATUS_CLOSED


pytestmark = pytest.mark.sno

ALL_CNV_PODS = [
    BRIDGE_MARKER,
    CDI_APISERVER,
    CDI_DEPLOYMENT,
    CDI_OPERATOR,
    CDI_UPLOADPROXY,
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    HCO_OPERATOR,
    HCO_WEBHOOK,
    HOSTPATH_PROVISIONER_OPERATOR,
    HOSTPATH_PROVISIONER,
    HOSTPATH_PROVISIONER_CSI,
    HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD,
    KUBE_CNI_LINUX_BRIDGE_PLUGIN,
    KUBEMACPOOL_CERT_MANAGER,
    KUBEMACPOOL_MAC_CONTROLLER_MANAGER,
    NMSTATE_CERT_MANAGER,
    NMSTATE_HANDLER,
    NMSTATE_WEBHOOK,
    NODE_MAINTENANCE_OPERATOR,
    SSP_OPERATOR,
    VIRT_API,
    VIRT_CONTROLLER,
    VIRT_TEMPLATE_VALIDATOR,
    VIRT_OPERATOR,
    VIRT_HANDLER,
]


@pytest.fixture()
def cnv_pods_by_type(request, cnv_pods):
    return [pod for pod in cnv_pods if pod.name.startswith(request.param)]


@pytest.mark.polarion("CNV-7261")
def test_no_new_cnv_pods_added(cnv_pods):
    new_pods = [
        pod.name
        for pod in cnv_pods
        if list(filter(pod.name.startswith, ALL_CNV_PODS)) == []
    ]
    assert not new_pods, f"New cnv pod: {new_pods}, has been added."


@pytest.mark.parametrize(
    "cnv_pods_by_type",
    [
        pytest.param(
            BRIDGE_MARKER,
            marks=pytest.mark.polarion("CNV-7891"),
            id="test_priority_class_bridge_marker",
        ),
        pytest.param(
            CDI_APISERVER,
            marks=pytest.mark.polarion("CNV-7892"),
            id="test_priority_class_cdi_apiserver",
        ),
        pytest.param(
            CDI_DEPLOYMENT,
            marks=pytest.mark.polarion("CNV-7893"),
            id="test_priority_class_cdi_deployment",
        ),
        pytest.param(
            CDI_OPERATOR,
            marks=pytest.mark.polarion("CNV-7894"),
            id="test_priority_class_cdi_operator",
        ),
        pytest.param(
            CDI_UPLOADPROXY,
            marks=pytest.mark.polarion("CNV-7895"),
            id="test_priority_class_cdi_upload_proxy",
        ),
        pytest.param(
            CLUSTER_NETWORK_ADDONS_OPERATOR,
            marks=pytest.mark.polarion("CNV-7896"),
            id="test_priority_class_cluster_network_addon_operator",
        ),
        pytest.param(
            HCO_OPERATOR,
            marks=pytest.mark.polarion("CNV-7897"),
            id="test_priority_class_hco_operator",
        ),
        pytest.param(
            HCO_WEBHOOK,
            marks=pytest.mark.polarion("CNV-7898"),
            id="test_priority_class_hco_webhook",
        ),
        pytest.param(
            HOSTPATH_PROVISIONER_OPERATOR,
            marks=pytest.mark.polarion("CNV-7899"),
            id="test_priority_class_hpp_operator",
        ),
        pytest.param(
            HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD,
            marks=pytest.mark.polarion("CNV-7900"),
            id="test_priority_class_hyperconverged_cluster_cli_download",
        ),
        pytest.param(
            KUBE_CNI_LINUX_BRIDGE_PLUGIN,
            marks=pytest.mark.polarion("CNV-7901"),
            id="test_priority_class_kube_cni_linux_bridge_plugin",
        ),
        pytest.param(
            KUBEMACPOOL_CERT_MANAGER,
            marks=pytest.mark.polarion("CNV-7902"),
            id="test_priority_class_kubemacpool_cert_manager",
        ),
        pytest.param(
            KUBEMACPOOL_MAC_CONTROLLER_MANAGER,
            marks=pytest.mark.polarion("CNV-7903"),
            id="test_priority_class_kubemacpool_mac_controller_manager",
        ),
        pytest.param(
            NMSTATE_CERT_MANAGER,
            marks=pytest.mark.polarion("CNV-7904"),
            id="test_priority_class_nmstate_cert_manager",
        ),
        pytest.param(
            NMSTATE_HANDLER,
            marks=pytest.mark.polarion("CNV-7905"),
            id="test_priority_class_nmstate_handler",
        ),
        pytest.param(
            NMSTATE_WEBHOOK,
            marks=pytest.mark.polarion("CNV-7906"),
            id="test_priority_class_nmstate_webhook",
        ),
        pytest.param(
            NODE_MAINTENANCE_OPERATOR,
            marks=(
                pytest.mark.polarion("CNV-7907"),
                pytest.mark.bugzilla(
                    2008960, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
            ),
            id="test_priority_class_node_maintenence_operator",
        ),
        pytest.param(
            SSP_OPERATOR,
            marks=pytest.mark.polarion("CNV-7908"),
            id="test_priority_class_ssp_operator",
        ),
        pytest.param(
            VIRT_API,
            marks=pytest.mark.polarion("CNV-7909"),
            id="test_priority_class_virt_api",
        ),
        pytest.param(
            VIRT_CONTROLLER,
            marks=pytest.mark.polarion("CNV-7910"),
            id="test_priority_class_virt_controller",
        ),
        pytest.param(
            VIRT_HANDLER,
            marks=pytest.mark.polarion("CNV-7911"),
            id="test_priority_class_virt_handler",
        ),
        pytest.param(
            VIRT_OPERATOR,
            marks=pytest.mark.polarion("CNV-7912"),
            id="test_priority_class_virt_operator",
        ),
        pytest.param(
            VIRT_TEMPLATE_VALIDATOR,
            marks=pytest.mark.polarion("CNV-7913"),
            id="test_priority_class_virt_template_validator",
        ),
    ],
    indirect=True,
)
def test_pods_priority_class_value(cnv_pods_by_type):
    validate_cnv_pods_priority_class_name_exists(pod_list=cnv_pods_by_type)
    validate_priority_class_value(pod_list=cnv_pods_by_type)


@pytest.mark.parametrize(
    "request_field",
    [
        pytest.param(
            "cpu",
            marks=(pytest.mark.polarion("CNV-7306")),
            id="test_pods_resource_request_cpu",
        ),
        pytest.param(
            "memory",
            marks=(pytest.mark.polarion("CNV-7307")),
            id="test_pods_resource_request_memory",
        ),
    ],
)
def test_pods_resource_request_cpu(cnv_pods, request_field):
    validate_cnv_pods_resource_request(cnv_pods=cnv_pods, request_field=request_field)


@pytest.mark.parametrize(
    "cpu_min_value",
    [
        pytest.param(
            5,
            marks=(pytest.mark.polarion("CNV-7341")),
            id="test_pods_resource_request_cpu",
        ),
    ],
)
def test_pods_resource_request_cpu_value(cnv_pods, cpu_min_value):
    """Test validates that resources.requests.cpu value for all cnv pods meet minimum threshold requirement"""
    cpu_error = {}
    for pod in cnv_pods:
        invalid_cpu = validate_cnv_pod_cpu_min_value(
            cnv_pod=pod, cpu_min_value=cpu_min_value
        )
        if invalid_cpu:
            cpu_error[pod.name] = invalid_cpu
    assert not cpu_error, f"For following pods invalid cpu values found: {cpu_error}"
