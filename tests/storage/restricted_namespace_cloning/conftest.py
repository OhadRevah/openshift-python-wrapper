# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV Storage restricted namespace cloning tests
"""
import pytest
from ocp_resources.namespace import Namespace

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
