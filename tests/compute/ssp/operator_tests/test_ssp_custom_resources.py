# -*- coding: utf-8 -*-

import logging

import pytest
from resources.custom_resource_definition import CustomResourceDefinition


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def crd_resources(default_client):
    return CustomResourceDefinition.get(dyn_client=default_client)


@pytest.fixture(scope="class")
def ssp_resource(request, crd_resources):
    ssp_resource = request.param
    LOGGER.info(f"Get SSP {ssp_resource} resource.")
    for resource in crd_resources:
        if ssp_resource in resource.name:
            return resource

    return False


def get_failed_resource_conditions(resource):
    """ Check resource conditions; return failed conditions """
    return [i for i in resource.instance.status.conditions if i["status"] != "True"]


class TestSSPCustomResources:
    @pytest.mark.parametrize(
        "ssp_resource",
        [
            pytest.param(
                "kubevirtcommontemplatesbundles",
                marks=(pytest.mark.polarion("CNV-3771")),
            ),
            pytest.param(
                "kubevirtnodelabellerbundles", marks=(pytest.mark.polarion("CNV-3773")),
            ),
            pytest.param(
                "kubevirttemplatevalidators", marks=(pytest.mark.polarion("CNV-3774")),
            ),
        ],
        indirect=True,
    )
    def test_verify_ssp_crd_existence(self, ssp_resource):
        assert ssp_resource, "CRD was not found."

    @pytest.mark.parametrize(
        "ssp_resource",
        [
            pytest.param(
                "kubevirtcommontemplatesbundles",
                marks=(pytest.mark.polarion("CNV-2957")),
            ),
            pytest.param(
                "kubevirtnodelabellerbundles", marks=(pytest.mark.polarion("CNV-3737")),
            ),
            pytest.param(
                "kubevirttemplatevalidators", marks=(pytest.mark.polarion("CNV-3736")),
            ),
        ],
        indirect=True,
    )
    def test_verify_ssp_crd_conditions(self, ssp_resource):
        failed_resource_conditions = get_failed_resource_conditions(
            resource=ssp_resource
        )
        assert (
            not failed_resource_conditions
        ), f"The following conditions failed: {failed_resource_conditions}."
