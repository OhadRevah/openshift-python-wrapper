# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV CDI tests
"""

import pytest
from resources.namespace import Namespace


@pytest.fixture(scope="session", autouse=True)
def storage_ns():
    with Namespace(name="cnv-cdi-ns") as ns:
        ns.wait_for_status(status=Namespace.Status.ACTIVE)
        yield ns
