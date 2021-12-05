# -*- coding: utf-8 -*-

import logging

import pytest
from ocp_resources.custom_resource_definition import CustomResourceDefinition
from ocp_resources.ssp import SSP

from tests.compute.utils import verify_pods_priority_class_value
from utilities.constants import VIRT_TEMPLATE_VALIDATOR
from utilities.infra import get_pod_by_name_prefix


pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]

CONDITIONS_DICT = {
    CustomResourceDefinition.Condition.PROGRESSING: "False",
    CustomResourceDefinition.Condition.AVAILABLE: "True",
    CustomResourceDefinition.Condition.DEGRADED: "False",
}
LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def ssp_resource(admin_client, hco_namespace):
    ssp_cr = list(
        SSP.get(
            dyn_client=admin_client,
            name="ssp-kubevirt-hyperconverged",
            namespace=hco_namespace.name,
        )
    )
    assert ssp_cr, "SSP CR was not found."
    return ssp_cr[0]


@pytest.fixture()
def pods_list_with_given_prefix(request, admin_client, hco_namespace):
    namespace_name = hco_namespace.name
    pods_prefix_name = request.param["pods_prefix_name"]
    pods_list_by_prefix = get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix=pods_prefix_name,
        namespace=namespace_name,
        get_all=True,
    )
    assert (
        pods_list_by_prefix
    ), f"Did not find pods with prefix: {pods_prefix_name} in namespace: {namespace_name}"
    return pods_list_by_prefix


@pytest.mark.polarion("CNV-3737")
def test_verify_ssp_crd_conditions(ssp_resource):
    LOGGER.info("Check SSP CR conditions.")
    resource_conditions = {
        condition.type: condition.status
        for condition in ssp_resource.instance.status.conditions
        if condition.type in CONDITIONS_DICT.keys()
    }
    assert (
        resource_conditions == CONDITIONS_DICT
    ), f"SSP CR conditions failed. Actual: {resource_conditions}, expected: {CONDITIONS_DICT}."


@pytest.mark.parametrize(
    "pods_list_with_given_prefix",
    [
        pytest.param(
            {"pods_prefix_name": "ssp-operator"}, marks=pytest.mark.polarion("CNV-7002")
        ),
        pytest.param(
            {"pods_prefix_name": VIRT_TEMPLATE_VALIDATOR},
            marks=pytest.mark.polarion("CNV-7003"),
        ),
    ],
    indirect=True,
)
def test_priority_class_value(pods_list_with_given_prefix):
    verify_pods_priority_class_value(
        pods=pods_list_with_given_prefix, expected_value="system-cluster-critical"
    )
