import logging
import re

import pytest
from ocp_resources.job import Job

from tests.install_upgrade_operators.pod_validation.utils import (
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
    HPP_POOL,
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


pytestmark = pytest.mark.sno

LOGGER = logging.getLogger(__name__)

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
    HPP_POOL,
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
def cnv_jobs(admin_client, hco_namespace):
    return [
        job.name
        for job in Job.get(dyn_client=admin_client, namespace=hco_namespace.name)
    ]


@pytest.fixture()
def cnv_pods_by_type(cnv_pod_matrix__function__, cnv_pods):
    pod_list = [
        pod for pod in cnv_pods if pod.name.startswith(cnv_pod_matrix__function__)
    ]
    if cnv_pod_matrix__function__ == HOSTPATH_PROVISIONER:
        pod_list = [
            pod
            for pod in pod_list
            if not (
                pod.name.startswith(HOSTPATH_PROVISIONER_OPERATOR)
                or pod.name.startswith(HOSTPATH_PROVISIONER_CSI)
            )
        ]
    LOGGER.info(f"Pods to be used: {[pod.name for pod in pod_list]}")
    return pod_list


@pytest.fixture()
def skip_host_path_provisioner_priority_class(cnv_pod_matrix__function__):
    if re.match(rf"{HOSTPATH_PROVISIONER}|{HPP_POOL}.*", cnv_pod_matrix__function__):
        pytest.skip(
            f"PriorityClassName test is not valid for {cnv_pod_matrix__function__} pods"
        )


@pytest.mark.polarion("CNV-7261")
def test_no_new_cnv_pods_added(cnv_pods, cnv_jobs):
    new_pods = [
        pod.name
        for pod in cnv_pods
        if list(filter(pod.name.startswith, ALL_CNV_PODS)) == []
        and pod.name not in cnv_jobs
    ]
    assert not new_pods, f"New cnv pod: {new_pods}, has been added."


@pytest.mark.polarion("CNV-7262")
def test_pods_priority_class_value(
    skip_host_path_provisioner_priority_class, cnv_pods_by_type
):
    validate_cnv_pods_priority_class_name_exists(pod_list=cnv_pods_by_type)
    validate_priority_class_value(pod_list=cnv_pods_by_type)


@pytest.mark.polarion("CNV-7306")
def test_pods_resource_request(
    cnv_pods_by_type,
    pod_resource_validation_matrix__function__,
):
    validate_cnv_pods_resource_request(
        cnv_pods=cnv_pods_by_type, resource=pod_resource_validation_matrix__function__
    )
