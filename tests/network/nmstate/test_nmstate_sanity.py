import logging

import pytest

from utilities.infra import BUG_STATUS_CLOSED, name_prefix
from utilities.network import EthernetNetworkConfigurationPolicy


LOGGER = logging.getLogger(__name__)
IP_LIST = [{"ip": "1.1.1.1", "prefix-length": 24}]


@pytest.mark.polarion("CNV-5721")
def test_no_ip(worker_node1, utility_pods, nodes_occupied_nics, nodes_available_nics):
    with EthernetNetworkConfigurationPolicy(
        name=f"no-ip-{name_prefix(worker_node1.name)}",
        node_selector=worker_node1.name,
        ipv4_dhcp=False,
        worker_pods=utility_pods,
        interfaces_name=[nodes_available_nics[worker_node1.name][0]],
        node_active_nics=nodes_occupied_nics[worker_node1.name],
    ):
        LOGGER.info("NNCP: Test no IP")


@pytest.mark.post_upgrade
@pytest.mark.polarion("CNV-5720")
def test_static_ip(
    worker_node1, utility_pods, nodes_occupied_nics, nodes_available_nics
):
    with EthernetNetworkConfigurationPolicy(
        name=f"static-ip-{name_prefix(worker_node1.name)}",
        node_selector=worker_node1.name,
        ipv4_dhcp=False,
        ipv4_enable=True,
        ipv4_addresses=IP_LIST,
        worker_pods=utility_pods,
        interfaces_name=[nodes_available_nics[worker_node1.name][0]],
        node_active_nics=nodes_occupied_nics[worker_node1.name],
    ):
        LOGGER.info("NMstate: Test with IP")


@pytest.mark.polarion("CNV-5722")
def test_dynamic_ip(
    worker_node1, utility_pods, nodes_occupied_nics, nodes_available_nics
):
    with EthernetNetworkConfigurationPolicy(
        name=f"dynamic-ip-{name_prefix(worker_node1.name)}",
        node_selector=worker_node1.name,
        ipv4_dhcp=True,
        ipv4_enable=True,
        worker_pods=utility_pods,
        interfaces_name=[nodes_available_nics[worker_node1.name][0]],
        node_active_nics=nodes_occupied_nics[worker_node1.name],
    ):
        LOGGER.info("NMstate: Test with dynamic IP")


@pytest.mark.bugzilla(
    1926143, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)
@pytest.mark.post_upgrade
@pytest.mark.polarion("CNV-5724")
def test_dns(worker_node1, utility_pods, nodes_occupied_nics):
    dns_resolver = {
        "config": {
            "search": ["example.com"],
            "server": ["8.8.8.8"],
        }
    }
    with EthernetNetworkConfigurationPolicy(
        name=f"dns-{name_prefix(worker_node1.name)}",
        node_selector=worker_node1.name,
        dns_resolver=dns_resolver,
    ):
        LOGGER.info("NMstate: Test DNS")


@pytest.mark.polarion("CNV-5725")
def test_static_route(
    worker_node1, utility_pods, nodes_occupied_nics, nodes_available_nics
):
    iface_name = nodes_available_nics[worker_node1.name][0]
    routes = {
        "config": [
            {
                "destination": "2.2.2.0/24",
                "metric": 150,
                "next-hop-address": "1.1.1.254",
                "next-hop-interface": iface_name,
            }
        ]
    }
    with EthernetNetworkConfigurationPolicy(
        name=f"static-route-{name_prefix(worker_node1.name)}",
        node_selector=worker_node1.name,
        ipv4_dhcp=False,
        ipv4_enable=True,
        ipv4_addresses=IP_LIST,
        worker_pods=utility_pods,
        interfaces_name=[iface_name],
        node_active_nics=nodes_occupied_nics[worker_node1.name],
        routes=routes,
    ):
        LOGGER.info("NMstate: Test static route")
