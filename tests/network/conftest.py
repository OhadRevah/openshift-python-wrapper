# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV network tests
"""

import pytest
from pytest_testconfig import config as py_config
from resources.pod import Pod

from utilities.network import get_ipv6_address, ip_version_data_from_matrix
from utilities.network import network_device_nocm as network_device


IPV6_STR = "ipv6"


@pytest.fixture(scope="session")
def bond_supported(hosts_common_available_ports):
    """
    Check if setup support BOND (have more then 2 NICs up)
    """
    return len(hosts_common_available_ports) >= 3


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
    hosts_common_available_ports,
    schedulable_nodes,
):
    params = request.param if hasattr(request, "param") else {}
    mtu = params.get("mtu")
    ports = [hosts_common_available_ports[0]] if multi_nics_nodes else []
    unique_index = next(index_number)
    interface_name = f"br{unique_index}test"
    iface = network_device(
        interface_type=bridge_device_matrix__class__,
        nncp_name=f"{interface_name}-nncp",
        interface_name=interface_name,
        network_utility_pods=utility_pods,
        nodes=schedulable_nodes,
        ports=ports,
        mtu=mtu,
    )
    iface.deploy()
    yield iface
    iface.clean_up()


@pytest.fixture(scope="session")
def dual_stack_cluster(admin_client):
    virt_handler_pod = list(
        Pod.get(
            dyn_client=admin_client,
            label_selector="kubevirt.io=virt-handler",
        )
    )[0]

    return get_ipv6_address(cnv_resource=virt_handler_pod) is not None


@pytest.fixture()
def skip_ipv6_if_not_dual_stack_cluster(
    request,
    dual_stack_cluster,
):
    if (
        ip_version_data_from_matrix(request=request) == IPV6_STR
        and not dual_stack_cluster
    ):
        pytest.skip(msg="IPv6 is not supported in this cluster")


@pytest.fixture(scope="module")
def ipv6_network_data(
    request,
    dual_stack_cluster,
):
    # dhcp4 should be enabled if it's a dual-stack flow, i.e. both IPv4 and IPv6 should be enabled
    # on the primary interface. The value returned from ip_version_data_from_matrix indicates that.
    if dual_stack_cluster:
        return {
            "ethernets": {
                "eth0": {
                    "dhcp4": ip_version_data_from_matrix(request) is not None,
                    "addresses": ["fd10:0:2::2/120"],
                    "gateway6": "fd10:0:2::1",
                },
            },
        }
