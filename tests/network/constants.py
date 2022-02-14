from utilities.constants import CLUSTER_NETWORK_ADDONS_OPERATOR, NMSTATE_HANDLER


DHCP_IP_RANGE_START = "10.200.3.3"
DHCP_IP_RANGE_END = "10.200.3.10"
EXPECTED_CNAO_COMP_NAMES = [
    "multus",
    NMSTATE_HANDLER,
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    "kubemacpool",
    "bridge",
    "nmstate",
    "ovs-cni",
]
