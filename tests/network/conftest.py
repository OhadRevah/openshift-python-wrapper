# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV network tests
"""

import os.path

import pytest

from resources.daemonset import DaemonSet
from resources.pod import Pod
from utilities import utils


class NetUtilityDaemonSet(DaemonSet):
    def _to_dict(self):
        res = super()._to_dict()
        res.update(
            utils.generate_yaml_from_template(
                file_=os.path.join(
                    os.path.dirname(__file__), "net-utility-daemonset.yaml"
                )
            )
        )
        return res


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
def net_utility_daemonset(default_client):
    """
    Deploy network utility daemonset into the kube-system namespace.

    This daemonset deploys a pod on every node with hostNetwork and the main usage is to run commands on the hosts.
    For example to create linux bridge and other components related to the host configuration.
    """
    with NetUtilityDaemonSet(name="net-utility", namespace="kube-system") as ds:
        ds.wait_until_deployed()
        yield ds


@pytest.fixture(scope="session")
def network_utility_pods(default_client):
    """
    Get network utility pods.
    When the tests start we deploy a pod on every host in the cluster using a daemonset.
    These pods have a label of cnv-test=net-utility and they are privileged pods with hostnetwork=true
    """
    return list(Pod.get(default_client, label_selector="cnv-test=net-utility"))


@pytest.fixture(scope="session")
def nodes_active_nics(network_utility_pods):
    """
    Get nodes active NICs. (Only NICs that are in UP state)
    First NIC is management NIC
    """
    nodes_nics = {}
    for pod in network_utility_pods:
        pod_container = pod.containers[0].name
        nodes_nics[pod.node.name] = []
        nics = pod.execute(
            command=[
                "bash",
                "-c",
                "ls -l /sys/class/net/ | grep -v virtual | grep net | rev | cut -d '/' -f 1 | rev",
            ],
            container=pod_container,
        )
        nics = nics.splitlines()
        default_gw = pod.execute(
            command=["ip", "route", "show", "default"], container=pod_container
        )
        for nic in nics:
            nic_state = pod.execute(
                command=["cat", f"/sys/class/net/{nic}/operstate"],
                container=pod_container,
            )
            if nic_state.strip() == "up":
                if nic in [i for i in default_gw.splitlines() if "default" in i][0]:
                    nodes_nics[pod.node.name].insert(0, nic)
                    continue

                nodes_nics[pod.node.name].append(nic)
    return nodes_nics


@pytest.fixture(scope="session")
def multi_nics_nodes(nodes_active_nics):
    """
    Check if nodes has more then 1 active NIC
    """
    return min(len(nics) for nics in nodes_active_nics.values()) > 2


@pytest.fixture(scope="session")
def bond_supported(network_utility_pods, nodes_active_nics):
    """
    Check if setup support BOND (have more then 2 NICs up)
    """
    return max([len(nodes_active_nics[i.node.name]) for i in network_utility_pods]) > 3


@pytest.fixture(scope="session")
def skip_if_no_multinic_nodes(multi_nics_nodes):
    if not multi_nics_nodes:
        pytest.skip("Only run on multi NICs node")
