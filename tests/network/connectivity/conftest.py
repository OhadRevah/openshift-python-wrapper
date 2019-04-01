# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV network tests
"""


def pytest_configure():
    import pytest
    pytest.active_node_nics = {}
    pytest.nodes_network_info = {}
    pytest.real_nics_env = False
    pytest.bond_support_env = False
    pytest.privileged_pods = None
    pytest.privileged_pod_container = None
    pytest.privileged_pods_ns = None
    pytest.ovs_del_br = None
    pytest.ovs_add_br = None
    pytest.ovs_add_port = None
