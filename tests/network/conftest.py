# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV network tests
"""

import pytest
from pytest_testconfig import config as py_config
from resources.pod import Pod
from tests.network.utils import bridge_device


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


@pytest.fixture(scope="class")
def skip_no_bond_support(bond_supported):
    if not bond_supported:
        pytest.skip(msg="No BOND support")


def get_index_number():
    num = 1
    while True:
        yield num
        num += 1


@pytest.fixture(scope="session")
def index_number():
    return get_index_number()


@pytest.fixture(scope="session")
def ovs_worker_pods(schedulable_nodes, default_client):
    """
    Get ovs-* pods, of worker (schedulable) nodes only, from openshift-sdn namespace.
    """

    def _ovs_pods(namespace, label):
        # First get all ovs-* pods.
        return list(Pod.get(default_client, namespace=namespace, label_selector=label))

    def _worker_pods(pods):
        # Now filter only the pods that run on worker nodes.
        worker_pods = []
        for pod in pods:
            for node in schedulable_nodes:
                if node.name == pod.node.name:
                    worker_pods.append(pod)
        return worker_pods

    ovs_pods = _ovs_pods(namespace="openshift-sdn", label="app=ovs")
    worker_pods = _worker_pods(pods=ovs_pods)
    if not worker_pods:
        ovs_pods = _ovs_pods(namespace=py_config["hco_namespace"], label="app=ovs-cni")
        worker_pods = _worker_pods(pods=ovs_pods)

    return worker_pods


@pytest.fixture(scope="class")
def ovs_lb_bridge(
    request,
    bridge_device_matrix__class__,
    index_number,
    ovs_worker_pods,
    schedulable_node_ips,
    multi_nics_nodes,
    network_utility_pods,
    nodes_active_nics,
    schedulable_nodes,
):
    params = request.param if hasattr(request, "param") else {}
    mtu = params.get("mtu")
    ports = (
        [nodes_active_nics[network_utility_pods[0].node.name][1]]
        if multi_nics_nodes
        else []
    )

    unique_index = next(index_number)
    bridge_name = f"br{unique_index}test"
    with bridge_device(
        bridge_type=bridge_device_matrix__class__,
        nncp_name=f"{bridge_name}-nncp",
        bridge_name=bridge_name,
        network_utility_pods=network_utility_pods,
        nodes=schedulable_nodes,
        ports=ports,
        mtu=mtu,
    ) as br:
        yield br
