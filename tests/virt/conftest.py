# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV VIRT tests
"""

import pytest
from tests import config
from resources.namespace import Namespace


@pytest.fixture(scope="session", autouse=True)
def init(request):
    """
    Create test namespaces
    """
    def fin():
        """
        Remove test namespaces
        """
        ns = Namespace(name=config.VIRT_NS)
        ns.delete(wait=True)
    request.addfinalizer(fin)

    ns = Namespace(name=config.VIRT_NS)
    ns.create(wait=True)
    ns.wait_for_status(status=Namespace.Status.ACTIVE)
