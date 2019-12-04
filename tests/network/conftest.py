# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV network tests
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def network_init(
    net_utility_daemonset,
    schedulable_node_ips,
    network_utility_pods,
    multi_nics_nodes,
    bond_supported,
):
    """
    Create network test namespaces
    """
    pass


@pytest.fixture(scope="session")
def bond_supported(network_utility_pods, multi_nics_nodes, nodes_active_nics):
    """
    Check if setup support BOND (have more then 2 NICs up)
    """
    return (
        max([len(nodes_active_nics[i.node.name]) for i in network_utility_pods]) > 3
        if multi_nics_nodes
        else False
    )


@pytest.fixture(scope="session")
def skip_if_no_multinic_nodes(multi_nics_nodes):
    if not multi_nics_nodes:
        pytest.skip("Only run on multi NICs node")


def get_index_number():
    num = 1
    while True:
        yield num
        num += 1


@pytest.fixture(scope="session")
def index_number():
    return get_index_number()
