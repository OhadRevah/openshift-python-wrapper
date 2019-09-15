# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV VIRT tests
"""

import pytest
from resources.namespace import Namespace


@pytest.fixture(scope="session", autouse=True)
def virt_namespace():
    with Namespace(name="cnv-virt-ns") as ns:
        ns.wait_for_status(status=Namespace.Status.ACTIVE)
        yield ns
