# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV network tests
"""

import pytest

from resources.namespace import NameSpace
from resources.node import Node
from resources.pod import Pod
from resources.resource import Resource
from tests.network import config
from tests.network.connectivity.ovs import config as ovs_config
from tests.network.utils import wait_for_pods_to_match_compute_nodes_number
from utilities import types, utils


@pytest.fixture(scope="session", autouse=True)
def network_init(
    create_namespaces,
    get_nodes_internal_ip,
    get_ovs_cni_pods,
    create_privileged_user,
    create_privileged_pods,
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
def get_ovs_cni_pods():
    """
    Get ovs-cni pods names
    """
    pytest.privileged_pods = [i for i in Pod().list_names() if i.startswith("ovs-cni")]
    if pytest.privileged_pods:
        pytest.privileged_pod_container = config.OVS_CNI_CONTAINER
        pytest.privileged_pods_ns = config.KUBE_SYSTEM_NS
        pytest.ovs_del_br = ovs_config.OVS_VSCTL_DEL_BR
        pytest.ovs_add_br = ovs_config.OVS_VSCTL_ADD_BR
        pytest.ovs_add_port = ovs_config.OVS_VSCTL_ADD_PORT
    else:
        pytest.privileged_pod_container = "privileged-test-pod"
        pytest.privileged_pods_ns = config.NETWORK_NS
        pytest.ovs_del_br = f"{ovs_config.OVS_VSCTL} del-br"
        pytest.ovs_add_br = f"{ovs_config.OVS_VSCTL} add-br"
        pytest.ovs_add_port = f"{ovs_config.OVS_VSCTL} add-port"


@pytest.fixture(scope='session')
def create_privileged_user(request):
    """
    Create privileged service account
    """
    if pytest.privileged_pods:
        return

    def fin():
        """
        Remove privileged service account
        """
        utils.run_oc_command(
            command="delete serviceaccount privileged-test-user",
            namespace=config.NETWORK_NS
        )
    request.addfinalizer(fin)

    assert utils.run_oc_command(
        command="create serviceaccount privileged-test-user",
        namespace=config.NETWORK_NS
    )[0]
    assert utils.run_oc_command(
        command="adm policy add-scc-to-user privileged -z privileged-test-user",
        namespace=config.NETWORK_NS
    )[0]


@pytest.fixture(scope='session')
def create_privileged_pods(request):
    """
    Create privileged pods
    """
    if pytest.privileged_pods:
        return

    pods_yaml = "tests/manifests/privileged-pod-ds.yml"
    resource = Resource(namespace=config.NETWORK_NS)

    def fin():
        resource.delete(yaml_file=pods_yaml, wait=True)
    request.addfinalizer(fin)

    compute_nodes = Node().list(label_selector="node-role.kubernetes.io/compute=true")
    assert resource.create(yaml_file=pods_yaml)
    wait_for_pods_to_match_compute_nodes_number(number_of_nodes=len(compute_nodes))
    privileged_pods = Pod().list_names(label_selector="app=privileged-test-pod")
    for idx, pod in enumerate(privileged_pods):
        pod_object = Pod(name=pod, namespace=pytest.privileged_pods_ns)
        assert pod_object.wait_for_status(status=types.RUNNING)
    pytest.privileged_pods = privileged_pods


@pytest.fixture(scope='session')
def get_nodes_internal_ip():
    """
    Get nodes internal IPs
    """
    compute_nodes = Node().list_names(label_selector="node-role.kubernetes.io/compute=true")
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
    for idx, pod in enumerate(pytest.privileged_pods):
        pod_object = Pod(name=pod, namespace=pytest.privileged_pods_ns)
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
