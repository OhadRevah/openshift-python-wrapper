import logging

from resources.node_network_state import NodeNetworkState


LOGGER = logging.getLogger(__name__)


def create(node, name, nics=None):
    node_network_state = NodeNetworkState(name=node)

    bond = {
        "name": name,
        "type": "bond",
        "state": "up",
        "link-aggregation": {
            "mode": "active-backup",
            "slaves": nics,
            "options": {"miimon": "120"},
        },
    }

    node_network_state.set_interface(bond)

    node_network_state.apply()

    node_network_state.wait_until_up(name)


def delete(node, name):
    bond = {"name": name, "type": "bond", "state": "absent"}

    node_network_state = NodeNetworkState(name=node)
    node_network_state.set_interface(bond)
    node_network_state.apply()

    node_network_state.wait_until_deleted(name)
