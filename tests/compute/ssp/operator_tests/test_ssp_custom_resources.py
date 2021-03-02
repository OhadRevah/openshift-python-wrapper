# -*- coding: utf-8 -*-

import logging

import pytest
from ocp_resources.custom_resource_definition import CustomResourceDefinition
from ocp_resources.ssp import SSP


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
