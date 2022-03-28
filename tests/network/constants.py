from utilities.constants import CLUSTER_NETWORK_ADDONS_OPERATOR


DHCP_IP_RANGE_START = "10.200.3.3"
DHCP_IP_RANGE_END = "10.200.3.10"
EXPECTED_CNAO_COMP_NAMES = [
    "multus",
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    "kubemacpool",
    "bridge",
    "ovs-cni",
]
HTTPBIN_IMAGE = "quay.io/verygoodsecurity/httpbin"
HTTPBIN_COMMAND = "gunicorn -b 0.0.0.0:8000 httpbin:app -k gevent"
PORT_8080 = 8080
SERVICE_MESH_PORT = 8000
