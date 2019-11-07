import pytest
from tests.network.utils import linux_bridge_nad
from utilities.network import LinuxBridgeNodeNetworkConfigurationPolicy, VXLANTunnel


BRIDGE_BR1 = "br1test"


@pytest.fixture(scope="class")
def dot1q_nad(namespace):
    with linux_bridge_nad(
        namespace=namespace, name="dot1q", bridge=BRIDGE_BR1
    ) as dot1q_nad:
        yield dot1q_nad


@pytest.fixture(scope="class")
def dhcp_nad(namespace):
    with linux_bridge_nad(
        namespace=namespace, name="dhcp-broadcast", bridge=BRIDGE_BR1
    ) as dhcp_broadcast:
        yield dhcp_broadcast


@pytest.fixture(scope="class")
def custom_eth_type_llpd_nad(namespace):
    with linux_bridge_nad(
        namespace=namespace, name="custom-eth-type-icmp", bridge=BRIDGE_BR1
    ) as custom_eth_type_icmp:
        yield custom_eth_type_icmp


@pytest.fixture(scope="class")
def mpls_nad(namespace):
    with linux_bridge_nad(namespace=namespace, name="mpls", bridge=BRIDGE_BR1) as mpls:
        yield mpls


@pytest.fixture(scope="class")
def all_nads(namespace, dot1q_nad, dhcp_nad, custom_eth_type_llpd_nad, mpls_nad):
    return [dot1q_nad.name, custom_eth_type_llpd_nad.name, dhcp_nad.name, mpls_nad.name]


@pytest.fixture(scope="class")
def bridge_device(network_utility_pods, multi_nics_nodes, nodes_active_nics):
    ports = (
        [nodes_active_nics[network_utility_pods[0].node.name][1]]
        if multi_nics_nodes
        else []
    )

    with LinuxBridgeNodeNetworkConfigurationPolicy(
        name="l2-linux-bridge",
        bridge_name=BRIDGE_BR1,
        worker_pods=network_utility_pods,
        ports=ports,
    ) as br:
        if not multi_nics_nodes:
            with VXLANTunnel(
                name="vxlan100",
                worker_pods=network_utility_pods,
                vxlan_id=10,
                master_bridge=br.bridge_name,
                nodes_nics=nodes_active_nics,
            ):
                yield br
        else:
            yield br
