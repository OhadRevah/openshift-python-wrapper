# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV network tests
"""

import pytest
from resources.pod import Pod
from tests.network.utils import bridge_device


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


@pytest.fixture(scope="session")
def ovs_worker_pods(nodes, default_client):
    """
    Get ovs-* pods, of worker (schedulable) nodes only, from openshift-sdn namespace.
   """
    # First get all ovs-* pods.
    ovs_pods = list(
        Pod.get(default_client, namespace="openshift-sdn", label_selector="app=ovs")
    )

    # Now filter only the pods that run on worker nodes.
    worker_pods = []
    for pod in ovs_pods:
        for node in nodes:
            if node.name == pod.node.name:
                worker_pods.append(pod)

    return worker_pods


@pytest.fixture(scope="class")
def ovs_lb_bridge(
    bridge_device_matrix,
    index_number,
    ovs_worker_pods,
    schedulable_node_ips,
    multi_nics_nodes,
    network_utility_pods,
    nodes_active_nics,
    nodes,
):
    ports = (
        [nodes_active_nics[network_utility_pods[0].node.name][1]]
        if multi_nics_nodes
        else []
    )

    unique_index = next(index_number)
    bridge_name = f"br{unique_index}test"
    with bridge_device(
        bridge_type=bridge_device_matrix,
        nncp_name=f"{bridge_name}-nncp",
        bridge_name=bridge_name,
        network_utility_pods=network_utility_pods,
        nodes=nodes,
        ports=ports,
        ovs_worker_pods=ovs_worker_pods,
        nodes_active_nics=nodes_active_nics,
        schedulable_node_ips=schedulable_node_ips,
        idx=100 + unique_index,
    ) as br:
        yield br
