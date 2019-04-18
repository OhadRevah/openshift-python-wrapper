# flake8: noqa: F401, F403, F405

from tests.network.connectivity.config import *

# YAMLS
OVS_NET_VLAN_100_YAML = "tests/manifests/network/ovs-vlan-100-net.yml"
OVS_NET_VLAN_200_YAML = "tests/manifests/network/ovs-vlan-200-net.yml"
OVS_NET_VLAN_300_YAML = "tests/manifests/network/ovs-vlan-300-net.yml"
OVS_NET_YAML = "tests/manifests/network/ovs-net.yml"
OVS_BOND_YAML = "tests/manifests/network/ovs-net-bond.yml"

# OVS
OVS_VSCTL = "ovs-vsctl"
OVS_VSCTL_ADD_BR = f"{OVS_VSCTL} add-br"
OVS_VSCTL_ADD_PORT = f"{OVS_VSCTL} add-port"
OVS_VSCTL_DEL_BR = f"{OVS_VSCTL} del-br"
