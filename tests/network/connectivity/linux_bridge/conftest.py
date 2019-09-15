import logging

import pytest
from tests.utils import Bridge


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def attach_linux_bridge_to_bond(bond1, network_utility_pods):
    """
    Create bridge and attach the BOND to it
    """
    if bond1:
        bond_bridge = "br1bond"
        with Bridge(
            name=bond_bridge, worker_pods=network_utility_pods, nic=bond1
        ) as br:
            yield br
    else:
        yield
