# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV network tests
"""

import pytest
from ocp_resources.pod import Pod

from utilities.infra import ClusterHosts
from utilities.network import get_ipv6_address, ip_version_data_from_matrix


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
