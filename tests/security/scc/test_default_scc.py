# -*- coding: utf-8 -*-

"""
Tests to check, the default Security Context Constraint
"""

import pytest
from resources.security_context_constraints import SecurityContextConstraints


@pytest.fixture(scope="module")
def privileged_scc():
    yield SecurityContextConstraints(name="privileged")


@pytest.mark.polarion("CNV-4439")
def test_users_in_privileged_scc_bz1831536(skip_not_openshift, privileged_scc):
    """
    Validate that Users in privileged SCC is not updated after installing CNV
    """
    assert len(privileged_scc.instance.users) == 2
    assert privileged_scc.instance.users[0] == "system:admin"
    assert (
        privileged_scc.instance.users[1]
        == "system:serviceaccount:openshift-infra:build-controller"
    )