# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV CDI tests
"""

import pytest
import tests.utils

from resources.namespace import Namespace
from resources.route import Route
from resources.storage_class import StorageClass


@pytest.fixture(scope="session", autouse=True)
def storage_ns():
    with Namespace(name="cnv-cdi-ns") as ns:
        ns.wait_for_status(status=Namespace.Status.ACTIVE)
        yield ns


@pytest.fixture()
def images_http_server():
    return tests.utils.get_images_http_server()


@pytest.fixture()
def upload_proxy_route(default_client):
    routes = Route.get(default_client)
    upload_route = None
    for route in routes:
        if route.service == 'cdi-uploadproxy':
            upload_route = route
    assert upload_route is not None
    yield upload_route


@pytest.fixture(scope='session')
def skip_no_default_sc(default_client):
    """
    Skip test if no default Storage Class defined
    """
    for sc in StorageClass.get(default_client):
        if sc.instance['metadata']['annotations']['storageclass.kubernetes.io/is-default-class'] == 'true':
            return
    pytest.skip("Skipping test, no default storage class configured")
