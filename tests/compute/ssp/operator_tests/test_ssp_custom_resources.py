# -*- coding: utf-8 -*-

import logging

import pytest
from pytest_testconfig import config as py_config
from resources.custom_resource_definition import CustomResourceDefinition
from resources.kubevirt_common_templates_bundle import KubevirtCommonTemplatesBundle
from resources.kubevirt_metrics_aggregation import KubevirtMetricsAggregation
from resources.kubevirt_node_labeller_bundle import KubevirtNodeLabellerBundle
from resources.kubevirt_template_validaotr import KubevirtTemplateValidator


CONDITIONS_DICT = {
    CustomResourceDefinition.Condition.PROGRESSING: "False",
    CustomResourceDefinition.Condition.AVAILABLE: "True",
    CustomResourceDefinition.Condition.DEGRADED: "False",
}
HCO_NAMESPACE = py_config["hco_namespace"]
LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def ssp_resource(request, admin_client):
    # Returns the requested resource passed in request.param
    cr = request.param["cr_name"]
    cr_namespace = request.param["namespace"]
    ssp_cr = list(cr.get(dyn_client=admin_client, namespace=cr_namespace))
    assert ssp_cr, f"CR {cr.kind} was not found in namespace {cr_namespace}."
    return ssp_cr[0]


@pytest.mark.parametrize(
    "ssp_resource",
    [
        pytest.param(
            {"cr_name": KubevirtCommonTemplatesBundle, "namespace": "openshift"},
            marks=(pytest.mark.polarion("CNV-2957")),
        ),
        pytest.param(
            {"cr_name": KubevirtNodeLabellerBundle, "namespace": HCO_NAMESPACE},
            marks=(pytest.mark.polarion("CNV-3737")),
        ),
        pytest.param(
            {"cr_name": KubevirtTemplateValidator, "namespace": HCO_NAMESPACE},
            marks=(pytest.mark.polarion("CNV-3736")),
        ),
        pytest.param(
            {"cr_name": KubevirtMetricsAggregation, "namespace": HCO_NAMESPACE},
            marks=(pytest.mark.polarion("CNV-4470")),
        ),
    ],
    indirect=True,
)
def test_verify_ssp_crd_conditions(ssp_resource):
    LOGGER.info(f"Check {ssp_resource.name} conditions.")
    resource_conditions = {
        condition.type: condition.status
        for condition in ssp_resource.instance.status.conditions
        if condition.type in CONDITIONS_DICT.keys()
    }
    assert (
        resource_conditions == CONDITIONS_DICT
    ), f"The following conditions failed: {resource_conditions}."
