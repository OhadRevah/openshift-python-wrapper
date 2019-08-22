import logging

import pytest
from resources.node_network_configuration_policy import NodeNetworkConfigurationPolicy
from resources.node_network_state import NodeNetworkState
from resources.utils import TimeoutExpiredError


LOGGER = logging.getLogger(__name__)


class BondNodeNetworkConfigurationPolicy(NodeNetworkConfigurationPolicy):
    def __init__(self, name, bond_name, nics, nodes):
        super().__init__(name=name)
        self.bond_name = bond_name
        self.nodes = nodes
        self.nics = nics
        self.bond = None

    def _to_dict(self):
        if not self.bond:
            self.bond = {
                "name": self.bond_name,
                "type": "bond",
                "state": "up",
                "link-aggregation": {
                    "mode": "active-backup",
                    "slaves": self.nics,
                    "options": {"miimon": "120"},
                },
            }

        self.set_interface(self.bond)
        res = super()._to_dict()
        return res

    def __enter__(self):
        super().__enter__()
        for node in self.nodes:
            try:
                node_network_state = NodeNetworkState(name=node)
                node_network_state.wait_until_up(self.bond_name)
            except TimeoutExpiredError:
                self.clean_up()
                raise
        return self

    def clean_up(self):
        self._absent_interface()
        self.wait_for_bond_deleted()
        self.delete()

    def __exit__(self, exception_type, exception_value, traceback):
        self.clean_up()

    def _absent_interface(self):
        self.bond["state"] = "absent"
        self.set_interface(self.bond)
        self.apply()

    def wait_for_bond_deleted(self):
        for node in self.nodes:
            node_network_state = NodeNetworkState(name=node)
            node_network_state.wait_until_deleted(self.bond_name)


@pytest.fixture(scope="module")
def bond1(network_utility_pods, bond_supported, nodes_active_nics):
    """
    Create BOND if setup support BOND
    """
    bond_name = "bond1"
    LOGGER.info(f"Creating bond {bond_name}")

    if bond_supported:
        with BondNodeNetworkConfigurationPolicy(
            name="bond1nncp",
            bond_name=bond_name,
            nodes=[i.node.name for i in network_utility_pods],
            nics=nodes_active_nics[network_utility_pods[0].node.name][2:4],
        ):
            yield bond_name
    else:
        yield None
