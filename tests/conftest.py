# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV tests
"""

import os

import kubernetes
import pytest
from openshift.dynamic import DynamicClient
from pytest_testconfig import config as py_config

from resources.node import Node
from resources.pod import Pod, ExecOnPodError


def pytest_configure():
    pytest.privileged_pods = []


def pytest_collection_modifyitems(session, config, items):
    """
    Add polarion test case it from tests to junit xml
    """
    for item in items:
        for marker in item.iter_markers(name='polarion'):
            test_id = marker.args[0]
            item.user_properties.append(('polarion-testcase-id', test_id))

        for marker in item.iter_markers(name='bugzilla'):
            test_id = marker.args[0]
            item.user_properties.append(('bugzilla', test_id))

        for marker in item.iter_markers(name='jira'):
            test_id = marker.args[0]
            item.user_properties.append(('jira', test_id))


def pytest_runtest_makereport(item, call):
    """
    incremental tests implementation
    """
    if "incremental" in item.keywords:
        if call.excinfo is not None:
            parent = item.parent
            parent._previousfailed = item


def pytest_runtest_setup(item):
    """
    Use incremental
    """
    if "incremental" in item.keywords:
        previousfailed = getattr(item.parent, "_previousfailed", None)
        if previousfailed is not None:
            pytest.xfail("previous test failed (%s)" % previousfailed.name)


@pytest.fixture(scope="session", autouse=True)
def junitxml_polarion(request):
    """
    Add polarion needed attributes to junit xml

    export as os environment:
        POLARION_CUSTOM_PLANNEDIN
        POLARION_TESTRUN_ID
    """
    if request.config.pluginmanager.hasplugin('junitxml'):
        my_junit = getattr(request.config, "_xml", None)
        if my_junit:
            my_junit.add_global_property('polarion-custom-isautomated', 'True')
            my_junit.add_global_property('polarion-testrun-status-id', 'inprogress')
            my_junit.add_global_property('polarion-custom-plannedin', os.getenv('POLARION_CUSTOM_PLANNEDIN'))
            my_junit.add_global_property('polarion-user-id', 'cnvqe')
            my_junit.add_global_property('polarion-project-id', 'CNV')
            my_junit.add_global_property('polarion-response-myproduct', 'cnv-test-run')
            my_junit.add_global_property('polarion-testrun-id', os.getenv('POLARION_TESTRUN_ID'))


@pytest.fixture(scope="session", autouse=True)
def default_client():
    """
    Get DynamicClient
    """
    return DynamicClient(kubernetes.config.new_client_from_config())


@pytest.fixture(scope='session')
def schedulable_node_ips(default_client):
    """
    Store all kubevirt.io/schedulable=true IPs
    """
    node_ips = {}
    for node in Node.get(
        default_client, label_selector="kubevirt.io/schedulable=true"
    ):
        for addr in node.instance.status.addresses:
            if addr.type == "InternalIP":
                node_ips[node.name] = addr.address
    return node_ips


@pytest.fixture(scope='session')
def get_privileged_pods(default_client):
    """
    Get ovs-cni pods names
    """
    for pod in Pod.get(default_client, label_selector=py_config['priviliged_pod_label_selector']):
        node = pod.node()
        if [i for i in node.instance.metadata.labels.keys() if 'worker' in i]:
            pytest.privileged_pods.append(pod)
            pod_containers = pod.containers()
            if pod_containers:
                pytest.privileged_pod_container = pod_containers[0].name

    assert pytest.privileged_pods, "No privileged pods found"


@pytest.fixture(scope='session')
def nodes_active_nics(get_privileged_pods):
    """
    Get nodes active NICs. (Only NICs that are in UP state)
    excluding the management NIC.
    """
    nodes_nics = {}
    for pod in pytest.privileged_pods:
        pod_container = pod.containers()[0].name
        node_name = pod.node().name
        nodes_nics[node_name] = []
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
            #  Exclude management NIC
            if nic_state.strip() == "up":
                if nic in [i for i in default_gw.splitlines() if 'default' in i][0]:
                    continue

                nodes_nics[pod.name].append(nic)
    return nodes_nics


@pytest.fixture(scope='session')
def is_bare_metal(get_privileged_pods):
    """
    Check if the cluster deployed on bare-metal hosts
    """
    for pod in pytest.privileged_pods:
        try:
            pod.execute(
                command=[
                    "bash", "-c",
                    "dmesg | grep -c 'Booting paravirtualized kernel on bare hardware'"
                ], container=pod.containers()[0].name
            )
        except ExecOnPodError:
            return False
    return True


@pytest.fixture(scope='session')
def bond_supported(is_bare_metal, nodes_active_nics):
    """
    Check if setup support BOND (have more then 2 NICs up)
    """
    return max(
        [len(nodes_active_nics[i.node().name]) for i in pytest.privileged_pods]
    ) > 2
