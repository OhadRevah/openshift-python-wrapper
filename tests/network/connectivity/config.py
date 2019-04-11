# flake8: noqa: F401, F403, F405

from tests.network.config import *

# VMS
CLOUD_INIT = {
    "bootcmd": ["dnf install -y iperf3 qemu-guest-agent"],
    "runcmd": ["systemctl start qemu-guest-agent"]
}
VMS = {
    "vm-fedora-1": {
        "cloud_init": CLOUD_INIT,
        "interfaces": {
            BRIDGE_BR1: ["192.168.0.1"],
            BRIDGE_BR1VLAN100: ["192.168.1.1"],
            BRIDGE_BR1VLAN200: ["192.168.2.1"],
        },
        "bonds": {
            BRIDGE_BR1BOND: ["192.168.3.1"],
        }
    },
    "vm-fedora-2": {
        "cloud_init": CLOUD_INIT,
        "interfaces": {
            BRIDGE_BR1: ["192.168.0.2"],
            BRIDGE_BR1VLAN100: ["192.168.1.2"],
            BRIDGE_BR1VLAN300: ["192.168.2.2"],
        },
        "bonds": {
            BRIDGE_BR1BOND: ["192.168.3.2"],
        }
    }
}

# VXLAN
VXLAN_10 = "vxlan10"

# BOND
BOND_1 = "bond1"
IP_LINK_INTERFACE_DOWN = "ip link set {interface} down"
IP_LINK_INTERFACE_UP = "ip link set {interface} up"
IP_LINK_ADD_BOND = f"ip link add {BOND_1} type bond"
IP_LINK_SET_BOND_PARAMS = f"ip link set {BOND_1} type bond miimon 100 mode active-backup"

# CLEANUP
ALL_BRIDGES = [BRIDGE_BR1, BRIDGE_BR1BOND]
