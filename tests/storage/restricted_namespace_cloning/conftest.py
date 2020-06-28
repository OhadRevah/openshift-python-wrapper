# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV Storage restricted namespace cloning tests
"""
import pytest
from resources.namespace import Namespace
from utilities.infra import Images


DV_PARAMS = {
    "dv_name": "source-dv",
    "source": "http",
    "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
    "dv_size": "500Mi",
}
NAMESPACE_PARAMS = {"unprivileged_client": None}


@pytest.fixture(scope="module")
def api_group():
    return "rbac.authorization.k8s.io"


@pytest.fixture(scope="module")
def unprivileged_user_username():
    return "unprivileged-user"


@pytest.fixture(scope="module")
def dst_ns():
    with Namespace(name="restricted-namespace-destination-namespace") as ns:
        ns.wait_for_status(status=Namespace.Status.ACTIVE, timeout=120)
        yield ns


@pytest.fixture(scope="module")
def skip_when_no_unprivileged_client_available(unprivileged_client):
    if not unprivileged_client:
        pytest.skip(msg="No unprivileged client available, skipping test")
