# flake8: noqa: F401, F403, F405

from tests.config import *


#  GENERAL
OVS_CNI = "ovs-cni"
OVS_CNI_CONTAINER = "ovs-cni-marker"
KUBE_SYSTEM_NS = "kube-system"
OPENSHIFT_SDN_NS = "openshift-sdn"

# LINUX BRIDGE CRDS YAMLS
LINUX_BRIDGE_VLAN_100_YAML = "tests/manifests/network/bridge-vlan-100-net.yml"
LINUX_BRIDGE_VLAN_200_YAML = "tests/manifests/network/bridge-vlan-200-net.yml"
LINUX_BRIDGE_VLAN_300_YAML = "tests/manifests/network/bridge-vlan-300-net.yml"
LINUX_BRIDGE_BOND_YAML = "tests/manifests/network/bridge-net-bond.yml"
LINUX_BRIDGE_YAML = "tests/manifests/network/bridge-net.yml"

# BRIDGE
BRIDGE_BR1 = "br1"
BRIDGE_BR1BOND = "br1bond"
BRIDGE_BR1VLAN100 = "br1vlan100"
BRIDGE_BR1VLAN200 = "br1vlan200"
BRIDGE_BR1VLAN300 = "br1vlan300"
