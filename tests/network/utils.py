import contextlib
import logging
import re

from resources.node_network_state import NodeNetworkState
from resources.sriov_network_node_state import SriovNetworkNodeState
from resources.utils import TimeoutExpiredError, TimeoutSampler
from utilities import console
from utilities.network import NETWORK_DEVICE_TYPE, SRIOV


LOGGER = logging.getLogger(__name__)


def _console_ping(src_vm, dst_ip, packetsize=None):
    ping_cmd = f"ping -w 3 {dst_ip}"
    if packetsize:
        ping_cmd += f" -s {packetsize} -M do"
    with console.Fedora(vm=src_vm) as src_vm_console:
        src_vm_console.sendline(ping_cmd)
        while True:
            line = src_vm_console.readline()
            m = re.search(b"([0-9]+)% packet loss, ", line)
            if m is not None:
                LOGGER.info(f"ping returned {m.string.strip()}")
                return m.groups()


def assert_ping_successful(src_vm, dst_ip, packetsize=None):
    assert _console_ping(src_vm, dst_ip, packetsize)[0] == b"0"


def assert_no_ping(src_vm, dst_ip, packetsize=None):
    assert _console_ping(src_vm, dst_ip, packetsize)[0] == b"100"


def nmcli_add_con_cmds(iface, ip):
    return [
        f"nmcli con add type ethernet con-name {iface} ifname {iface}",
        f"nmcli con mod {iface} ipv4.addresses {ip}/24 "
        f"ipv4.method manual connection.autoconnect-priority 1 ipv6.method ignore",
        f"nmcli con up {iface}",
    ]


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
    ipv4_dhcp=None,
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
