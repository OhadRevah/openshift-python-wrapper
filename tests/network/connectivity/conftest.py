import logging

import pytest
from tests.network.nmstate import bond


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def bond1(network_utility_pods, bond_supported, nodes_active_nics):
    """
    Create BOND if setup support BOND
    """
    bond_name = "bond1"

    LOGGER.info(f"Creating bond {bond_name}")

    if bond_supported:

        for pod in network_utility_pods:
            node_name = pod.node.name
            bond.create(
                node=node_name, name=bond_name, nics=nodes_active_nics[node_name][2:4]
            )

        yield bond_name

        for pod in network_utility_pods:
            node_name = pod.node.name
            bond.delete(node=pod.node.name, name=bond_name)
    else:
        yield None
