import contextlib
import logging

from resources.node_network_state import NodeNetworkState
from resources.sriov_network_node_state import SriovNetworkNodeState
from resources.utils import TimeoutExpiredError, TimeoutSampler

from utilities.network import NETWORK_DEVICE_TYPE, SRIOV, console_ping


LOGGER = logging.getLogger(__name__)
DHCP_SERVER_CONF_FILE = """
cat <<EOF >> /etc/dhcp/dhcpd.conf
default-lease-time 3600;
max-lease-time 7200;
authoritative;
subnet {DHCP_IP_SUBNET}.0 netmask 255.255.255.0 {{
option subnet-mask 255.255.255.0;
range {DHCP_IP_RANGE_START} {DHCP_IP_RANGE_END};
}}
EOF
"""


def assert_no_ping(src_vm, dst_ip, packetsize=None):
    assert console_ping(src_vm, dst_ip, packetsize)[0] == b"100"


def running_vmi(vm):
    vm.start(wait=True)
    vm.vmi.wait_until_running()
    return vm.vmi


@contextlib.contextmanager
def network_device(
    interface_type,
    nncp_name,
    network_utility_pods,
    nodes=None,
    interface_name=None,
    ports=None,
    mtu=None,
    node_selector=None,
    ipv4_enable=False,
    ipv4_dhcp=False,
    priority=None,
    namespace=None,
):
    nodes_names = [node_selector] if node_selector else [node.name for node in nodes]
    worker_pods = [pod for pod in network_utility_pods if pod.node.name in nodes_names]
    kwargs = {
        "name": nncp_name,
        "mtu": mtu,
    }
    if interface_type == SRIOV:
        snns = SriovNetworkNodeState(name=worker_pods[0].node.name)
        iface = snns.interfaces[0]
        kwargs["namespace"] = namespace
        kwargs["pf_names"] = snns.iface_name(iface=iface)
        kwargs["root_devices"] = snns.pciaddress(iface=iface)
        kwargs["num_vfs"] = snns.totalvfs(iface=iface)
        kwargs["priority"] = priority or 99

    else:
        kwargs["bridge_name"] = interface_name
        kwargs["worker_pods"] = worker_pods
        kwargs["ports"] = ports
        kwargs["node_selector"] = node_selector
        kwargs["ipv4_enable"] = ipv4_enable
        kwargs["ipv4_dhcp"] = ipv4_dhcp

    with NETWORK_DEVICE_TYPE[interface_type](**kwargs) as iface:
        yield iface


def update_cloud_init_extra_user_data(cloud_init_data, cloud_init_extra_user_data):
    for k, v in cloud_init_extra_user_data.items():
        if k not in cloud_init_data:
            cloud_init_data.update(cloud_init_extra_user_data)
        else:
            cloud_init_data[k] = cloud_init_data[k] + v


def wait_for_address_on_iface(worker_pod, iface_name):
    """
    This function returns worker's ip else throws 'resources.utils.TimeoutExpiredError: Timed Out:
    if function passed in func argument failed.
    """
    sample = None
    log = "Worker ip address for {iface_name} : {sample}"
    samples = TimeoutSampler(
        timeout=120,
        sleep=1,
        func=NodeNetworkState(worker_pod.node.name).ipv4,
        iface=iface_name,
    )
    try:
        for sample in samples:
            if sample:
                LOGGER.info(log.format(iface_name=iface_name, sample=sample))
                return sample
    except TimeoutExpiredError:
        LOGGER.error(log.format(iface_name=iface_name, sample=sample))
        raise


def get_worker_pod(network_utility_pods, worker_node):
    """
    This function will return a pod based on the node specified as an argument.
    """
    for pod in network_utility_pods:
        if pod.node.name == worker_node.name:
            return pod
