import logging

import pytest
from tests.utils import LinuxBridgeNodeNetworkConfigurationPolicy


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def attach_linux_bridge_to_bond(bond1, network_utility_pods):
    """
    Create bridge and attach the BOND to it
    """
    if bond1:
        bond_bridge = "br1bond"
        with LinuxBridgeNodeNetworkConfigurationPolicy(
            name="bridge-to-bond",
            bridge_name=bond_bridge,
            worker_pods=network_utility_pods,
            ports=[bond1],
        ) as br:
            yield br
    else:
        yield
