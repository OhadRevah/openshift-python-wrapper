# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV CDI tests
"""

import pytest
import tests.utils

from resources.namespace import Namespace


@pytest.fixture(scope="session", autouse=True)
def storage_ns():
    with Namespace(name="cnv-cdi-ns") as ns:
        ns.wait_for_status(status=Namespace.Status.ACTIVE)
        yield ns


@pytest.fixture()
def images_http_server():
    return tests.utils.get_images_http_server()
