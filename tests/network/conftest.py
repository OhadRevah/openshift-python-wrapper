# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV network tests
"""

import pytest

from resources.namespace import Namespace
from tests.network import config


@pytest.fixture(scope="session", autouse=True)
def network_init(
    create_namespaces,
    schedulable_node_ips,
    get_privileged_pods,
    is_bare_metal,
    bond_supported,
):
    """
    Create network test namespaces
    """
    pass


@pytest.fixture(scope='session')
def create_namespaces(request):
    def fin():
        """
        Remove network test namespaces
        """
        ns = Namespace(name=config.NETWORK_NS)
        ns.delete(wait=True)
    request.addfinalizer(fin)

    ns = Namespace(name=config.NETWORK_NS)
    ns.create(wait=True)
    ns.wait_for_status(status=Namespace.Status.ACTIVE)
