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
                singular_name="template",
                label_selector="template.kubevirt.io/type=base",
            )
        )
    ]


@pytest.mark.polarion("CNV-1069")
def test_base_templates_annotations(get_base_templates):
    """
    Check all CNV templates exists, by label: template.kubevirt.io/type=base
    """
    missing_templates = set(virt_config.CNV_TEMPLATES_NAME) - set(get_base_templates)
    new_changed_templates = set(get_base_templates) - set(
        virt_config.CNV_TEMPLATES_NAME
    )

    assert len(missing_templates) == 0, f"Missing templates {missing_templates}"
    assert (
        len(new_changed_templates) == 0
    ), f"Found new/changed templates {new_changed_templates}"
