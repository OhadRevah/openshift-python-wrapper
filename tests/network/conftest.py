# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV network tests
"""

import pytest
from pytest_testconfig import config as py_config

from resources.namespace import Namespace
from resources.node import Node
from resources.pod import Pod
from tests.network import config


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
        ns = Namespace(name=config.NETWORK_NS)
        ns.delete(wait=True)
    request.addfinalizer(fin)

    ns = Namespace(name=config.NETWORK_NS)
    ns.create(wait=True)
    ns.wait_for_status(status=Namespace.Status.ACTIVE)


@pytest.fixture(scope='session')
def get_privileged_pods(default_client):
    """
    Get ovs-cni pods names
    """
    for pod in Pod.get_resources(default_client, label_selector=py_config['priviliged_pod_label_selector']):
        node = pod.node()
        if [i for i in node.instance.metadata.labels.keys() if 'worker' in i]:
            pytest.privileged_pods.append(pod)
            pod_containers = pod.containers()
            if pod_containers:
                pytest.privileged_pod_container = pod_containers[0].name

    assert pytest.privileged_pods, "No privileged pods found"


@pytest.fixture(scope='session')
def get_nodes_internal_ip(default_client):
    """
    Get nodes internal IPs
    """
    for node in Node.get_resources(default_client, label_selector="kubevirt.io/schedulable=true"):
        for addr in node.instance.status.addresses:
            if addr.type == "InternalIP":
                pytest.nodes_network_info[node.name] = addr.address
                break


@pytest.fixture(scope='session')
def is_bare_metal():
    """
    Check if setup is on bare-metal
    """
    for pod in pytest.privileged_pods:
        pod_container = pod.containers()[0].name
        pytest.active_node_nics[pod.name] = []
        assert pod.wait_for_status(status=Pod.Status.RUNNING)
        nics = pod.execute(
            command=[
                "bash", "-c",
                "ls -l /sys/class/net/ | grep -v virtual | grep net | rev | cut -d '/' -f 1 | rev"
            ], container=pod_container
        )
        nics = nics.splitlines()
        default_gw = pod.execute(
            command=["ip", "route", "show", "default"], container=pod_container
        )
        for nic in nics:
            nic_state = pod.execute(
                command=["cat", f"/sys/class/net/{nic}/operstate"], container=pod_container
            )
            if nic_state.strip() == "up":
                if nic in [i for i in default_gw.splitlines() if 'default' in i][0]:
                    continue

                pytest.active_node_nics[pod.name].append(nic)
                driver = pod.execute(
                    command=[
                        "bash", "-c",
                        f"basename $(readlink -f /sys/class/net/{nic}/device/driver/module/)"
                    ], container=pod_container
                )
                pytest.real_nics_env = driver.strip() != "virtio_net"


@pytest.fixture(scope='session')
def is_bond_supported():
    """
    Check if setup support BOND (have more then 2 NICs up)
    """
    pytest.bond_support_env = max(
        [len(pytest.active_node_nics[i.name]) for i in pytest.privileged_pods]
    ) > 2
