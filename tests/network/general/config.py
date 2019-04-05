# flake8: noqa: F401, F403, F405

from tests.network.config import *

VETH_REMOVED_VMS = {
    "vm-veth-remove-1": {
        "interfaces": {
            BRIDGE_BR1: ["192.168.0.1"],
            BRIDGE_BR1VLAN100: ["192.168.1.1"]
        }
    },
    "vm-veth-remove-2": {
        "interfaces": {
            BRIDGE_BR1: ["192.168.0.2"],
            BRIDGE_BR1VLAN100: ["192.168.1.2"]
        }
    }
}
