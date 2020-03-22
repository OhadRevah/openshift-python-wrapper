"""
Test VLAN network interfaces on hosts network only (not on CNV VM).
"""
import logging

import pytest
from resources.utils import TimeoutExpiredError, TimeoutSampler
from tests.network.host_network.vlan.conftest import DHCP_IP_SUBNET


LOGGER = logging.getLogger(__name__)

TEST_TIMEOUT = 30
SAMPLING_INTERVAL = 1


def sampling_handler(
    sampled_func, timeout=TEST_TIMEOUT, interval=SAMPLING_INTERVAL, err_msg=None
):
    try:
        sampled_ip_search = TimeoutSampler(
            timeout=timeout, sleep=interval, func=sampled_func
        )
        for sample in sampled_ip_search:
            if sample:
                return

    except TimeoutExpiredError:
        if err_msg is not None:
            LOGGER.error(err_msg)
        raise


def assert_vlan_dynamic_ip(iface_name, workers_ssh_executors, dhcp_clients_list):
    def _find_vlan_ip():
        for node in dhcp_clients_list:
            vlan_ip = workers_ssh_executors[node.name].network.find_ip_by_int(
                iface_name
            )
            if (vlan_ip is None) or (DHCP_IP_SUBNET not in vlan_ip):
                return False
        return True

    err_msg = (
        f"VLAN interface {iface_name} in some nodes was not assigned a dynamic IP."
    )
    sampling_handler(sampled_func=_find_vlan_ip, err_msg=err_msg)


def assert_vlan_iface_no_ip(iface_name, workers_ssh_executors, no_dhcp_client_list):
    for node in no_dhcp_client_list:
        vlan_ip = workers_ssh_executors[node.name].network.find_ip_by_int(iface_name)
        if vlan_ip is not None:
            return False
    return True


@pytest.mark.polarion("CNV-3451")
def test_vlan_connectivity_on_all_hosts(
    skip_when_one_node,
    skip_rhel7_workers,
    skip_if_workers_vms,
    namespace,
    vlan_iface_on_all_nodes,
    dhcp_server,
    dhcp_client_nodes,
    dhcp_client,
    disable_vlan_ipv4_dhcp,
    workers_ssh_executors,
):
    """
    Test that VLAN NICs on all hosts except for the DHCP server host are assigned a dynamic IP address.
    """
    assert_vlan_dynamic_ip(
        iface_name=vlan_iface_on_all_nodes.iface_name,
        workers_ssh_executors=workers_ssh_executors,
        dhcp_clients_list=dhcp_client_nodes,
    )


@pytest.mark.polarion("CNV-3452")
def test_vlan_connectivity_on_one_host(
    skip_when_one_node,
    skip_rhel7_workers,
    skip_if_workers_vms,
    namespace,
    vlan_iface_on_all_nodes,
    dhcp_server,
    dhcp_client_nodes,
    dhcp_client,
    dhcp_client_on_one_node,
    remove_node_selector,
    workers_ssh_executors,
):
    """
    Test that VLAN NIC on only one host (which is not the DHCP server host) is assigned a dynamic IP address.
    """
    no_dhcp_client_list = list(
        filter(lambda x: x.name is dhcp_client_on_one_node.name, dhcp_client_nodes)
    )
    assert_vlan_dynamic_ip(
        iface_name=vlan_iface_on_all_nodes.iface_name,
        workers_ssh_executors=workers_ssh_executors,
        dhcp_clients_list=[dhcp_client_on_one_node],
    )
    assert_vlan_iface_no_ip(
        iface_name=vlan_iface_on_all_nodes.iface_name,
        workers_ssh_executors=workers_ssh_executors,
        no_dhcp_client_list=no_dhcp_client_list,
    )


@pytest.mark.polarion("CNV-3463")
def test_neg_no_connectivity_between_different_vlan_tags(
    skip_when_one_node,
    skip_rhel7_workers,
    skip_if_workers_vms,
    namespace,
    vlan_iface_on_all_nodes,
    dhcp_server,
    selected_dhcp_client,
    vlan_iface_on_one_node_with_different_tag,
    remove_node_selector,
    workers_ssh_executors,
):
    """
    Negative: Test that VLAN NICs (that are created using k8s-nmstate) with different tags have no connectivity
    between them.
    """
    with pytest.raises(TimeoutExpiredError):
        assert_vlan_dynamic_ip(
            iface_name=vlan_iface_on_one_node_with_different_tag.iface_name,
            workers_ssh_executors=workers_ssh_executors,
            dhcp_clients_list=[selected_dhcp_client],
        )


@pytest.mark.polarion("CNV-3469")
def test_vlan_connectivity_over_bond_on_all_hosts(
    skip_when_one_node,
    skip_rhel7_workers,
    skip_if_workers_vms,
    skip_no_bond_support,
    namespace,
    vlan_iface_over_bond_on_all_nodes,
    dhcp_server,
    dhcp_client_over_bond,
    dhcp_client_nodes,
    workers_ssh_executors,
):
    """
    Test that VLAN NICs which are configured over bond interfaces, on all hosts except for the DHCP server host
    are assigned a dynamic IP address.
    """
    assert_vlan_dynamic_ip(
        iface_name=vlan_iface_over_bond_on_all_nodes.iface_name,
        workers_ssh_executors=workers_ssh_executors,
        dhcp_clients_list=dhcp_client_nodes,
    )


"""
This test must remain the last one, otherwise there will be no complete tear-down for this module,
and resources will remain hanging.
"""


@pytest.mark.last
@pytest.mark.polarion("CNV-3462")
def test_vlan_deletion(
    skip_when_one_node,
    skip_rhel7_workers,
    skip_if_workers_vms,
    namespace,
    vlan_iface_on_all_nodes,
    schedulable_worker_pods,
):
    """
    Test that VLAN NICs that are created using k8s-nmstate can be successfully deleted.
    """
    vlan_iface_on_all_nodes.clean_up()
    for pod in schedulable_worker_pods:
        ip_addr_out = pod.execute(
            command=[
                "bash",
                "-c",
                f"ip addr show {vlan_iface_on_all_nodes.iface_name} |  wc -l",
            ]
        )
        assert int(ip_addr_out.strip()) == 0, (
            f"VLAN interface {vlan_iface_on_all_nodes.iface_name} was not deleted from node "
            f"{pod.node.name}."
        )
