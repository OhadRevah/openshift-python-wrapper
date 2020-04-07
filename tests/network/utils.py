import contextlib
import logging
import re

from pytest_testconfig import config as py_config
from utilities import console
from utilities.network import (
    LinuxBridgeNetworkAttachmentDefinition,
    LinuxBridgeNodeNetworkConfigurationPolicy,
    OvsBridgeNetworkAttachmentDefinition,
    OvsBridgeNodeNetworkConfigurationPolicy,
)


LOGGER = logging.getLogger(__name__)
LINUX_BRIDGE = "linux-bridge"
OVS = "ovs"
BRIDGE_DEVICE_TYPE = {
    LINUX_BRIDGE: LinuxBridgeNodeNetworkConfigurationPolicy,
    OVS: OvsBridgeNodeNetworkConfigurationPolicy,
}
BRIDGE_NAD_TYPE = {
    LINUX_BRIDGE: LinuxBridgeNetworkAttachmentDefinition,
    OVS: OvsBridgeNetworkAttachmentDefinition,
}


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
def bridge_device(
    bridge_type,
    nncp_name,
    bridge_name,
    network_utility_pods,
    nodes,
    ports=None,
    mtu=None,
    node_selector=None,
    ipv4_dhcp=None,
):
    schedulable_worker_pods = [
        pod
        for pod in network_utility_pods
        if pod.node.name in [node.name for node in nodes]
    ]
    with BRIDGE_DEVICE_TYPE[bridge_type](
        name=nncp_name,
        bridge_name=bridge_name,
        worker_pods=schedulable_worker_pods,
        ports=ports,
        mtu=mtu,
        node_selector=node_selector,
        ipv4_dhcp=ipv4_dhcp,
    ) as br:
        yield br


@contextlib.contextmanager
def bridge_nad(
    nad_type, nad_name, bridge_name, namespace, tuning=None, vlan=None, mtu=None
):
    kwargs = {
        "namespace": namespace.name,
        "name": nad_name,
        "bridge_name": bridge_name,
        "vlan": vlan,
        "mtu": mtu,
    }
    if nad_type == LINUX_BRIDGE:
        cni_type = py_config["template_defaults"]["linux_bridge_cni_name"]
        tuning_type = (
            py_config["template_defaults"]["bridge_tuning_name"] if tuning else None
        )
        kwargs["cni_type"] = cni_type
        kwargs["tuning_type"] = tuning_type

    with BRIDGE_NAD_TYPE[nad_type](**kwargs) as nad:
        yield nad


def update_cloud_init_extra_user_data(cloud_init_data, cloud_init_extra_user_data):
    for k, v in cloud_init_extra_user_data.items():
        if k not in cloud_init_data:
            cloud_init_data.update(cloud_init_extra_user_data)
        else:
            cloud_init_data[k] = cloud_init_data[k] + v
