# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV CDI tests
"""

import pytest
from resources.namespace import Namespace


@pytest.fixture(scope="session", autouse=True)
def storage_ns(request):
    """
    Create tests namespace
    """
    ns = Namespace(name="cnv-cdi-ns")
    try:
        assert ns.create(wait=True)
        assert ns.wait_for_status(status=Namespace.Status.ACTIVE)
        yield ns
    finally:
        ns.delete(wait=True)
