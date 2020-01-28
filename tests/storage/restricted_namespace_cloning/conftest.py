# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV Storage restricted namespace cloning tests
"""
import pytest


@pytest.fixture(scope="module")
def api_group():
    return "rbac.authorization.k8s.io"


@pytest.fixture(scope="module")
def unprivileged_user_username():
    return "unprivileged-user"
