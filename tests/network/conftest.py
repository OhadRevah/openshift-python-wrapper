# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV network tests
"""

import pytest

from resources.namespace import NameSpace
from resources.node import Node
from resources.pod import Pod
from tests.network import config
from utilities import types


@pytest.fixture(scope="session", autouse=True)
def network_init(
    create_namespaces,
    get_nodes_internal_ip,
    get_privileged_pods,
    is_bare_metal,
    is_bond_supported,
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
        ns = NameSpace(name=config.NETWORK_NS)
        ns.delete(wait=True)
    request.addfinalizer(fin)

    ns = NameSpace(name=config.NETWORK_NS)
    ns.create(wait=True)
    ns.wait_for_status(status=types.ACTIVE)
    ns.work_on()


@pytest.fixture(scope='session')
def get_privileged_pods():
    """
    Get ovs-cni pods names
    """
    privileged_pods = [
        i for i in Pod().list_names(namespace=config.OPENSHIFT_SDN_NS) if i.startswith("ovs-")
    ]
    for pod in privileged_pods:
        pod_object = Pod(name=pod, namespace=config.OPENSHIFT_SDN_NS)
        node = pod_object.node()
        node_obj = Node(name=node, namespace=config.OPENSHIFT_SDN_NS)
        node_data = node_obj.get()
        if [i for i in node_data.metadata.labels.keys() if 'worker' in i]:
            pytest.privileged_pods.append(pod)
            pod_containers = pod_object.containers()
            if pod_containers:
                pytest.privileged_pod_container = pod_containers[0].name

    assert pytest.privileged_pods, "No privileged pods found"


@pytest.fixture(scope='session')
def get_nodes_internal_ip():
    """
    Get nodes internal IPs
    """
    compute_nodes = Node().list_names(label_selector="kubevirt.io/schedulable=true")
    for node in compute_nodes:
        node_obj = Node(name=node)
        node_info = node_obj.get()
        for addr in node_info.status.addresses:
            if addr.type == "InternalIP":
                pytest.nodes_network_info[node] = addr.address
                break
    assert len(pytest.nodes_network_info.keys()) == len(compute_nodes)


@pytest.fixture(scope='session')
def is_bare_metal():
    """
    Check if setup is on bare-metal
    """
    for pod in pytest.privileged_pods:
        pod_object = Pod(name=pod, namespace=config.OPENSHIFT_SDN_NS)
        pod_container = pytest.privileged_pod_container
        pytest.active_node_nics[pod] = []
        assert pod_object.wait_for_status(status=types.RUNNING)
        err, nics = pod_object.exec(command=config.GET_NICS_CMD, container=pod_container)
        assert err
        nics = nics.splitlines()
        err, default_gw = pod_object.exec(command="ip route show default", container=pod_container)
        assert err
        for nic in nics:
            err, nic_state = pod_object.exec(
                command=f"cat /sys/class/net/{nic}/operstate", container=pod_container
            )
            assert err
            if nic_state.strip() == "up":
                if nic in [i for i in default_gw.splitlines() if 'default' in i][0]:
                    continue

                pytest.active_node_nics[pod].append(nic)
                err, driver = pod_object.exec(
                    command=config.CHECK_NIC_DRIVER_CMD.format(nic=nic), container=pod_container
                )
                assert err
                pytest.real_nics_env = driver.strip() != "virtio_net"


@pytest.fixture(scope='session')
def is_bond_supported():
    """
    Check if setup support BOND (have more then 2 NICs up)
    """
    pytest.bond_support_env = max(
        [len(pytest.active_node_nics[i]) for i in pytest.privileged_pods]
    ) > 2
