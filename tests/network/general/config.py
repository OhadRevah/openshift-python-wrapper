# flake8: noqa: F401, F403, F405

from tests.network.config import *

# TEST_VETH REMOVED AFTER VMS DELETED
VETH_REMOVED_INTERFACES = {
    "interfaces": {
            BRIDGE_BR1: [],
            BRIDGE_BR1VLAN100: []
        }
}
VETH_REMOVED_VMS = {
    "vm-veth-remove-1": VETH_REMOVED_INTERFACES,
    "vm-veth-remove-2": VETH_REMOVED_INTERFACES,
}

# TEST PERFORMANCE
PERFORMANCE_CLOUD_INIT = {
    "cloud_init": {
        "runcmd": [
            "sed -i s/'PasswordAuthentication no'/'PasswordAuthentication yes'/g /etc/ssh/sshd_config",
            "systemctl restart sshd",
            "systemctl start qemu-guest-agent",
        ],
        "bootcmd": ["dnf install -y qemu-guest-agent"],
    }
}
PERFORMANCE_VMS = {
    "vm-performance-1": PERFORMANCE_CLOUD_INIT,
    "vm-performance-2": PERFORMANCE_CLOUD_INIT,
}
