import pytest
from tests.network.utils import ovs_bridge_nad


@pytest.fixture(scope="class")
def dot1q_nad(namespace, ovs_bridge_on_all_nodes):
    with ovs_bridge_nad(
        namespace=namespace, name="dot1q", bridge=ovs_bridge_on_all_nodes.bridge_name
    ) as dot1q_nad:
        yield dot1q_nad


@pytest.fixture(scope="class")
def dhcp_nad(namespace, ovs_bridge_on_all_nodes):
    with ovs_bridge_nad(
        namespace=namespace,
        name="dhcp-broadcast",
        bridge=ovs_bridge_on_all_nodes.bridge_name,
    ) as dhcp_broadcast:
        yield dhcp_broadcast


@pytest.fixture(scope="class")
def custom_eth_type_llpd_nad(namespace, ovs_bridge_on_all_nodes):
    with ovs_bridge_nad(
        namespace=namespace,
        name="custom-eth-type-icmp",
        bridge=ovs_bridge_on_all_nodes.bridge_name,
    ) as custom_eth_type_icmp:
        yield custom_eth_type_icmp


@pytest.fixture(scope="class")
def mpls_nad(namespace, ovs_bridge_on_all_nodes):
    with ovs_bridge_nad(
        namespace=namespace, name="mpls", bridge=ovs_bridge_on_all_nodes.bridge_name
    ) as mpls:
        yield mpls


@pytest.fixture(scope="class")
def all_nads(namespace, dot1q_nad, dhcp_nad, custom_eth_type_llpd_nad, mpls_nad):
    return [dot1q_nad.name, custom_eth_type_llpd_nad.name, dhcp_nad.name, mpls_nad.name]
