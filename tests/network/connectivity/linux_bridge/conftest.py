import pytest

import logging
from tests.network.utils import Bridge

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def attach_linux_bridge_to_bond(create_bond, network_utility_pods, bond_supported):
    """
    Create bridge and attach the BOND to it
    """
    if bond_supported:
        bond_name = "bond1"
        bond_bridge = "br1bond"
        with Bridge(
            name=bond_bridge, worker_pods=network_utility_pods, nic=bond_name
        ) as br:
            yield br
    else:
        yield
