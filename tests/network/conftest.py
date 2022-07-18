# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV network tests
"""

import pytest
from ocp_resources.deployment import Deployment
from ocp_resources.namespace import Namespace
from ocp_resources.pod import Pod
from openshift.dynamic.exceptions import ResourceNotFoundError

from tests.network.constants import BRCNV
from tests.network.utils import vm_for_brcnv_tests
from utilities.constants import (
    IPV6_STR,
    ISTIO_SYSTEM_DEFAULT_NS,
    KUBEMACPOOL_MAC_CONTROLLER_MANAGER,
    OVS_BRIDGE,
    SRIOV,
    VIRT_HANDLER,
)
from utilities.infra import ClusterHosts, ExecCommandOnPod
from utilities.network import ip_version_data_from_matrix, network_nad


@pytest.fixture(scope="session")
def bond_supported(hosts_common_available_ports):
    """
    Check if setup support BOND (have more then 2 NICs up)
    """
    return len(hosts_common_available_ports) > 2


@pytest.fixture(scope="class")
def skip_no_bond_support(bond_supported):
    if not bond_supported:
        pytest.skip(msg="No BOND support")


@pytest.fixture(scope="module")
def skip_if_workers_bms(workers_type):
    if workers_type == ClusterHosts.Type.PHYSICAL:
        pytest.skip(msg="This test(s) cannot run on BM cluster.")


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
    """
    set vlan tags based on tlv lab.
    with this change it should work with both rdu and tlv labs.
    fixture returns a dictionary with keys of the current supported vlan tags range (1000-1019).
    """
    tag_id = 1000
    return {f"{tag_id + idx}": tag_id + idx for idx in range(20)}


@pytest.fixture(scope="session")
def virt_handler_pod(admin_client):
    for pod in Pod.get(
        dyn_client=admin_client,
        label_selector=f"{Pod.ApiGroup.KUBEVIRT_IO}={VIRT_HANDLER}",
    ):
        return pod

    raise ResourceNotFoundError(f"No {VIRT_HANDLER} Pod found.")


@pytest.fixture(scope="session")
def dual_stack_cluster(ipv4_supported_cluster, ipv6_supported_cluster):
    return ipv4_supported_cluster and ipv6_supported_cluster


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


@pytest.fixture()
def worker_node1_pod_executor(utility_pods, worker_node1):
    return ExecCommandOnPod(utility_pods=utility_pods, node=worker_node1)


@pytest.fixture(scope="module")
def dual_stack_network_data(dual_stack_cluster):
    if dual_stack_cluster:
        return {
            "ethernets": {
                "eth0": {
                    "dhcp4": True,
                    "addresses": ["fd10:0:2::2/120"],
                    "gateway6": "fd10:0:2::1",
                },
            },
        }


@pytest.fixture(scope="module")
def kmp_deployment(hco_namespace):
    return Deployment(
        namespace=hco_namespace.name, name=KUBEMACPOOL_MAC_CONTROLLER_MANAGER
    )


@pytest.fixture(scope="session")
def istio_system_namespace(admin_client):
    return Namespace(name=ISTIO_SYSTEM_DEFAULT_NS, client=admin_client).exists


@pytest.fixture()
def skip_if_service_mesh_not_installed(istio_system_namespace):
    # Service mesh not installed if the cluster doesn't have ISTIO-SYSTEM ns
    if not istio_system_namespace:
        pytest.skip(msg="Cannot run the test. Service Mesh not installed")


@pytest.fixture(scope="module")
def sriov_workers_node1(sriov_workers):
    """
    Get first worker nodes with SR-IOV capabilities
    """
    return sriov_workers[0]


@pytest.fixture(scope="class")
def sriov_workers_node2(sriov_workers):
    """
    Get second worker nodes with SR-IOV capabilities
    """
    return sriov_workers[1]


@pytest.fixture(scope="module")
def sriov_network(sriov_node_policy, namespace, sriov_namespace):
    """
    Create a SR-IOV network linked to SR-IOV policy.
    """
    with network_nad(
        nad_type=SRIOV,
        nad_name="sriov-test-network",
        sriov_resource_name=sriov_node_policy.resource_name,
        namespace=sriov_namespace,
        sriov_network_namespace=namespace.name,
    ) as sriov_network:
        yield sriov_network


@pytest.fixture(scope="class")
def skip_insufficient_sriov_workers(sriov_workers):
    """
    This function will make sure at least 2 worker nodes has SR-IOV capability
    else tests will be skip.
    """
    if len(sriov_workers) < 2:
        pytest.skip("Test requires at least 2 SR-IOV worker nodes")


@pytest.fixture(scope="module")
def brcnv_ovs_nad_vlan_1001(
    hyperconverged_ovs_annotations_enabled_scope_session,
    namespace,
):
    vlan_1001 = 1001
    with network_nad(
        namespace=namespace,
        nad_type=OVS_BRIDGE,
        nad_name=f"{BRCNV}-{vlan_1001}",
        interface_name=BRCNV,
        vlan=vlan_1001,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def brcnv_vma_with_vlan_1001(
    unprivileged_client,
    namespace,
    worker_node1,
    brcnv_ovs_nad_vlan_1001,
):
    yield from vm_for_brcnv_tests(
        vm_name="vma",
        namespace=namespace,
        unprivileged_client=unprivileged_client,
        nads=[brcnv_ovs_nad_vlan_1001],
        address_suffix=1,
        node_selector=worker_node1.hostname,
    )
