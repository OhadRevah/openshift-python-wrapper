# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV Storage restricted namespace cloning tests
"""
import pytest
from ocp_resources.namespace import Namespace

from tests.storage.restricted_namespace_cloning.constants import (
    PERMISSIONS_DST,
    PERMISSIONS_SRC,
    VERBS_DST,
    VERBS_SRC,
)
from tests.storage.utils import set_permissions
from utilities.constants import TIMEOUT_2MIN


@pytest.fixture(scope="module")
def api_group():
    return "rbac.authorization.k8s.io"


@pytest.fixture(scope="module")
def unprivileged_user_username():
    return "unprivileged-user"


@pytest.fixture(scope="module")
def dst_ns():
    with Namespace(name="restricted-namespace-destination-namespace") as ns:
        ns.wait_for_status(status=Namespace.Status.ACTIVE, timeout=TIMEOUT_2MIN)
        yield ns


@pytest.fixture(scope="module")
def skip_when_no_unprivileged_client_available(unprivileged_client):
    if not unprivileged_client:
        pytest.skip(msg="No unprivileged client available, skipping test")


@pytest.fixture()
def permissions_src(request, unprivileged_user_username, api_group, namespace):
    with set_permissions(
        role_name="datavolume-cluster-role-src",
        verbs=request.param[VERBS_SRC],
        permissions_to_resources=request.param[PERMISSIONS_SRC],
        binding_name="role_bind_src",
        namespace=namespace.name,
        subjects_name=unprivileged_user_username,
        subjects_api_group=api_group,
    ):
        yield


@pytest.fixture()
def permissions_dst(request, unprivileged_user_username, api_group, dst_ns):
    with set_permissions(
        role_name="datavolume-cluster-role-dst",
        verbs=request.param[VERBS_DST],
        permissions_to_resources=request.param[PERMISSIONS_DST],
        binding_name="role_bind_dst",
        namespace=dst_ns.name,
        subjects_name=unprivileged_user_username,
        subjects_api_group=api_group,
    ):
        yield
