import logging

from resources.node_network_state import NodeNetworkState


LOGGER = logging.getLogger(__name__)
SLEEP = 1
TIMEOUT = 120


def create(node, name, nic=None):
    ports = []
    if nic:
        ports = [
            {
                "name": nic,
                "stp-hairpin-mode": False,
                "stp-path-cost": 100,
                "stp-priority": 32,
            }
        ]

    bridge = {
        "name": name,
        "type": "linux-bridge",
        "state": "up",
        "bridge": {"options": {"stp": {"enabled": False}}, "port": ports},
    }

    node_network_state = NodeNetworkState(name=node)
    node_network_state.set_interface(bridge)
    node_network_state.apply()

    node_network_state.wait_until_up(name)


def delete(node, name):
    bridge = {"name": name, "type": "linux-bridge", "state": "absent"}

    node_network_state = NodeNetworkState(name=node)
    node_network_state.set_interface(bridge)
    node_network_state.apply()

    node_network_state.wait_until_deleted(name)
