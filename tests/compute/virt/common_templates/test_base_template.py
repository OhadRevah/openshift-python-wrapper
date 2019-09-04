# -*- coding: utf-8 -*-

"""
Base templates test
"""

import pytest

from resources.template import Template
from tests.compute.virt import config as virt_config


@pytest.fixture()
def get_base_templates(default_client):
    """ Return templates list by label """
    yield [
        template.name
        for template in list(
            Template.get(
                default_client,
                singular_name=Template.singular_name,
                label_selector="template.kubevirt.io/type=base",
            )
        )
    ]


@pytest.mark.polarion("CNV-1069")
def test_base_templates_annotations(get_base_templates):
    """
    Check all CNV templates exists, by label: template.kubevirt.io/type=base
    """
    assert len(get_base_templates) == len(virt_config.CNV_TEMPLATES_NAME), (
        f"Not all base CNV templates exists\n exist templates:\n "
        f"{get_base_templates} expected:\n {virt_config.CNV_TEMPLATES_NAME}",
    )
