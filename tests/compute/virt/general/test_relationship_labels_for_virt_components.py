import logging

import pytest
from ocp_resources.daemonset import DaemonSet
from ocp_resources.deployment import Deployment
from ocp_resources.resource import Resource
from openshift.dynamic.exceptions import ResourceNotFoundError

from utilities.constants import (
    HCO_OPERATOR,
    HCO_PART_OF_LABEL_VALUE,
    KUBEVIRT_HCO_NAME,
    MANAGED_BY_LABEL_VALUE_OLM,
    VIRT_API,
    VIRT_CONTROLLER,
    VIRT_HANDLER,
    VIRT_OPERATOR,
)


LOGGER = logging.getLogger(__name__)

APP_KUBERNETES_IO = Resource.ApiGroup.APP_KUBERNETES_IO
KUBEVIRT_IO = Resource.ApiGroup.KUBEVIRT_IO
MANAGED_BY_LABEL = f"{APP_KUBERNETES_IO}/managed-by"


def remove_irrelevant_labels(labels_dict):
    irrelevant_labels_list = [
        "controller-revision-hash",
        "pod-template-generation",
        "prometheus.kubevirt.io",
        "pod-template-hash",
        "olm.deployment-spec-hash",
        "olm.owner",
        "olm.owner.kind",
        "olm.owner.namespace",
        f"{Resource.ApiGroup.OPERATORS_COREOS_COM}/kubevirt-hyperconverged.openshift-cnv",
    ]

    for label in irrelevant_labels_list:
        labels_dict.pop(label, "")

    return labels_dict


def assert_custom_resource_labels(cr, expected_labels):
    cr_labels_dict = remove_irrelevant_labels(
        labels_dict=dict(cr.instance.metadata.labels)
    )
    assert (
        cr_labels_dict == expected_labels
    ), f"Labels mismatch!\nCurrent labels: {cr_labels_dict}\nExpected labels: {expected_labels}"


def assert_pods_labels(pods_list, expected_labels):
    for pod in pods_list:
        LOGGER.info(f"Verifying pod {pod.name} labels")
        pod_labels_dict = remove_irrelevant_labels(
            labels_dict=dict(pod.instance.metadata.labels)
        )
        assert (
            pod_labels_dict == expected_labels
        ), f"Labels mismatch!\nPod {pod.name} labels: {pod_labels_dict}\nExpected labels: {expected_labels}"


@pytest.fixture()
def virt_custom_resource(request, admin_client, hco_namespace):
    for resource in request.param["resource"].get(
        dyn_client=admin_client,
        name=request.param["name"],
        namespace=hco_namespace.name,
    ):
        return resource

    raise ResourceNotFoundError(
        f"No {request.param['name']} deployment/daemonset found"
    )


@pytest.fixture(scope="module")
def expected_labels_dicts(cnv_current_version):
    general_labels_dict = {
        f"{APP_KUBERNETES_IO}/component": "compute",
        f"{APP_KUBERNETES_IO}/version": cnv_current_version,
        f"{APP_KUBERNETES_IO}/part-of": HCO_PART_OF_LABEL_VALUE,
    }

    virt_api_pod_labels_dict = {
        **general_labels_dict,
        MANAGED_BY_LABEL: VIRT_OPERATOR,
        KUBEVIRT_IO: VIRT_API,
    }
    virt_api_deployment_labels_dict = {
        **virt_api_pod_labels_dict,
        f"{APP_KUBERNETES_IO}/name": VIRT_API,
    }

    virt_controller_pod_labels_dict = {
        **general_labels_dict,
        MANAGED_BY_LABEL: VIRT_OPERATOR,
        KUBEVIRT_IO: VIRT_CONTROLLER,
    }
    virt_controller_deployment_labels_dict = {
        **virt_controller_pod_labels_dict,
        f"{APP_KUBERNETES_IO}/name": VIRT_CONTROLLER,
    }

    virt_operator_deployment_labels_dict = {
        **general_labels_dict,
        MANAGED_BY_LABEL: MANAGED_BY_LABEL_VALUE_OLM,
    }
    virt_operator_pod_labels_dict = {
        **virt_operator_deployment_labels_dict,
        KUBEVIRT_IO: VIRT_OPERATOR,
        "name": VIRT_OPERATOR,
    }

    virt_handler_daemonset_labels_dict = virt_handler_pod_labels_dict = {
        **general_labels_dict,
        MANAGED_BY_LABEL: VIRT_OPERATOR,
        KUBEVIRT_IO: VIRT_HANDLER,
    }

    kubevirt_cr_labels_dict = {
        **general_labels_dict,
        "app": "kubevirt-hyperconverged",
        MANAGED_BY_LABEL: HCO_OPERATOR,
    }

    return {
        VIRT_API: {
            "cr": virt_api_deployment_labels_dict,
            "pod": virt_api_pod_labels_dict,
        },
        VIRT_CONTROLLER: {
            "cr": virt_controller_deployment_labels_dict,
            "pod": virt_controller_pod_labels_dict,
        },
        VIRT_OPERATOR: {
            "cr": virt_operator_deployment_labels_dict,
            "pod": virt_operator_pod_labels_dict,
        },
        VIRT_HANDLER: {
            "cr": virt_handler_daemonset_labels_dict,
            "pod": virt_handler_pod_labels_dict,
        },
        KUBEVIRT_HCO_NAME: {"cr": kubevirt_cr_labels_dict},
    }


@pytest.mark.parametrize(
    "virt_custom_resource, virt_pods",
    [
        pytest.param(
            {"resource": Deployment, "name": VIRT_API},
            VIRT_API,
            marks=pytest.mark.polarion("CNV-8017"),
            id=f"case: {VIRT_API}",
        ),
        pytest.param(
            {"resource": Deployment, "name": VIRT_CONTROLLER},
            VIRT_CONTROLLER,
            marks=pytest.mark.polarion("CNV-8019"),
            id=f"case: {VIRT_CONTROLLER}",
        ),
        pytest.param(
            {"resource": Deployment, "name": VIRT_OPERATOR},
            VIRT_OPERATOR,
            marks=pytest.mark.polarion("CNV-8021"),
            id=f"case: {VIRT_OPERATOR}",
        ),
        pytest.param(
            {"resource": DaemonSet, "name": VIRT_HANDLER},
            VIRT_HANDLER,
            marks=pytest.mark.polarion("CNV-8020"),
            id=f"case: {VIRT_HANDLER}",
        ),
    ],
    indirect=True,
)
def test_virt_resources_labels(virt_custom_resource, virt_pods, expected_labels_dicts):
    name = virt_custom_resource.name

    LOGGER.info(f"Verifying {name} deployment/daemonset labels")
    assert_custom_resource_labels(
        cr=virt_custom_resource, expected_labels=expected_labels_dicts[name]["cr"]
    )

    LOGGER.info(f"Verifying {name} pods labels")
    assert_pods_labels(
        pods_list=virt_pods, expected_labels=expected_labels_dicts[name]["pod"]
    )


@pytest.mark.polarion("CNV-8084")
def test_kubevirt_cr_labels(kubevirt_resource_scope_session, expected_labels_dicts):
    name = kubevirt_resource_scope_session.name

    LOGGER.info(f"Verifying {name} labels")
    assert_custom_resource_labels(
        cr=kubevirt_resource_scope_session,
        expected_labels=expected_labels_dicts[name]["cr"],
    )
