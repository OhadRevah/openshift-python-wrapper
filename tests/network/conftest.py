# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV network tests
"""

import pytest
from pytest_testconfig import config as py_config
from resources.pod import Pod
from tests.network.utils import network_device
from utilities.network import get_hosts_common_ports


@pytest.fixture(scope="session")
def bond_supported(utility_pods, multi_nics_nodes, nodes_available_nics):
    """
    Check if setup support BOND (have more then 2 NICs up)
    """
    return (
        max([len(nodes_available_nics[i.node.name]) for i in utility_pods]) > 3
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
def vlan_tag_id(index_number):
    # set vlan id based on tlv lab.
    # current supported range is between 1000-1019.
    # with this change it should work with both rdu and tlv labs.
    vlan_upper_range = 1020
    vlan_id = 999 + next(index_number)
    if vlan_id > vlan_upper_range:
        raise ValueError(f"VLAN ID: {vlan_id} is out of range")
    return vlan_id


@pytest.fixture(scope="session")
def ovs_worker_pods(schedulable_nodes, admin_client):
    """
    Get ovs-* pods, of worker (schedulable) nodes only, from openshift-sdn namespace.
    """

    def _ovs_pods(namespace, label):
        # First get all ovs-* pods.
        return list(Pod.get(admin_client, namespace=namespace, label_selector=label))

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
def network_interface(
    request,
    bridge_device_matrix__class__,
    index_number,
    ovs_worker_pods,
    schedulable_node_ips,
    multi_nics_nodes,
    utility_pods,
    nodes_available_nics,
    schedulable_nodes,
):
    params = request.param if hasattr(request, "param") else {}
    mtu = params.get("mtu")
    ports = (
        [get_hosts_common_ports(nodes_available_nics=nodes_available_nics)[0]]
        if multi_nics_nodes
        else []
    )
    unique_index = next(index_number)
    interface_name = f"br{unique_index}test"
    with network_device(
        interface_type=bridge_device_matrix__class__,
        nncp_name=f"{interface_name}-nncp",
        interface_name=interface_name,
        network_utility_pods=utility_pods,
        nodes=schedulable_nodes,
        ports=ports,
        mtu=mtu,
    ) as iface:
        yield iface
