# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV network tests
"""

import pytest
from kubernetes.dynamic.exceptions import NotFoundError
from ocp_resources.deployment import Deployment
from ocp_resources.pod import Pod

from utilities.constants import IPV4_STR, IPV6_STR, VIRT_HANDLER
from utilities.infra import ClusterHosts, ExecCommandOnPod
from utilities.network import (
    get_ip_from_vm_or_virt_handler_pod,
    ip_version_data_from_matrix,
)


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

    raise NotFoundError(f"No {VIRT_HANDLER} Pod found.")


@pytest.fixture(scope="session")
def ipv4_supported_cluster(virt_handler_pod):
    return get_ip_from_vm_or_virt_handler_pod(
        family=IPV4_STR, virt_handler_pod=virt_handler_pod
    )


@pytest.fixture(scope="session")
def ipv6_supported_cluster(virt_handler_pod):
    return get_ip_from_vm_or_virt_handler_pod(
        family=IPV6_STR, virt_handler_pod=virt_handler_pod
    )


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
        namespace=hco_namespace.name, name="kubemacpool-mac-controller-manager"
    )
