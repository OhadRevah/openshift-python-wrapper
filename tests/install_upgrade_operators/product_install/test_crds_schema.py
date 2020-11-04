# -*- coding: utf-8 -*-
import pytest
from resources.custom_resource_definition import CustomResourceDefinition


@pytest.fixture(scope="module")
def all_crd_resources(admin_client):
    """
    Returns List of CustomResourceDefinitions Resources.
    """
    return list(CustomResourceDefinition.get(admin_client, group="kubevirt.io"))


@pytest.mark.polarion("CNV-4695")
def test_check_crd_non_structural_schema(all_crd_resources):
    failed_crds = []
    for kubevirt_crd_resource in all_crd_resources:
        for resource_condition in kubevirt_crd_resource.instance.status.conditions:
            if resource_condition["NonStructuralSchema"]:
                failed_crds.append(kubevirt_crd_resource.name)

    assert not failed_crds, f"CRD is having Non Structual Schema {failed_crds}"
