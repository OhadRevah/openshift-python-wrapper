# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV virt common-templates tests
"""

import pytest
from resources.namespace import Namespace


@pytest.fixture(scope="module", autouse=True)
def namespace():
    with Namespace(name="common-templates-test") as ns:
        ns.wait_for_status(status=Namespace.Status.ACTIVE)
        yield ns
