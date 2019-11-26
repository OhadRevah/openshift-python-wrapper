import contextlib
import ipaddress
import logging
import re

from pytest_testconfig import config as py_config
from resources.utils import TimeoutExpiredError, TimeoutSampler
from utilities import console
from utilities.network import (
    LinuxBridgeNetworkAttachmentDefinition,
    LinuxBridgeNodeNetworkConfigurationPolicy,
    OvsBridgeNetworkAttachmentDefinition,
    OvsBridgeNodeNetworkConfigurationPolicy,
    OvsBridgeOverVxlan,
    VXLANTunnel,
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


@contextlib.contextmanager
def linux_bridge_nad(namespace, name, bridge, vlan=None, tuning=None, mtu=None):
    cni_type = py_config["template_defaults"]["linux_bridge_cni_name"]
    tuning_type = (
        py_config["template_defaults"]["bridge_tuning_name"] if tuning else None
    )
    with LinuxBridgeNetworkAttachmentDefinition(
        namespace=namespace.name,
        name=name,
        bridge_name=bridge,
        cni_type=cni_type,
        vlan=vlan,
        tuning_type=tuning_type,
        mtu=mtu,
    ) as nad:
        yield nad


@contextlib.contextmanager
def ovs_bridge_nad(namespace, name, bridge, vlan=None, mtu=None):
    # No need to extract the configuration for CNI type like in linux_bridge_nad, because the OVS CNI name is similar
    # in both upstream and downstream.

    with OvsBridgeNetworkAttachmentDefinition(
        namespace=namespace.name, name=name, bridge_name=bridge, vlan=vlan, mtu=mtu
    ) as nad:
        yield nad


class IpNotFound(Exception):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"IP address not found for interface {self.name}"


def get_vmi_ip_v4_by_name(vmi, name):
    sampler = TimeoutSampler(timeout=120, sleep=1, func=lambda: vmi.interfaces)
    try:
        for sample in sampler:
            for iface in sample:
                if iface.name == name:
                    for ipaddr in iface.ipAddresses:
                        ip = ipaddress.ip_interface(ipaddr)
                        if ip.version == 4:
                            return ip.ip
    except TimeoutExpiredError:
        raise IpNotFound(name)


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
    ports=None,
    nodes_active_nics=None,
    mtu=None,
    node_selector=None,
    schedulable_node_ips=None,
    ovs_worker_pods=None,
    idx=None,
):
    if bridge_type == OVS and not ports:
        with OvsBridgeOverVxlan(
            bridge_name=bridge_name,
            vxlan_iface_name=f"vxlan-ovs{idx}",
            ovs_worker_pods=ovs_worker_pods,
            remote_ips=schedulable_node_ips,
        ) as br:
            yield br

    else:
        with BRIDGE_DEVICE_TYPE[bridge_type](
            name=nncp_name,
            bridge_name=bridge_name,
            worker_pods=network_utility_pods,
            ports=ports,
            mtu=mtu,
            node_selector=node_selector,
        ) as br:
            if not ports:
                with VXLANTunnel(
                    name=f"vxlan{idx}",
                    worker_pods=network_utility_pods,
                    vxlan_id=idx,
                    master_bridge=br.bridge_name,
                    nodes_nics=nodes_active_nics,
                ):
                    yield br
            else:
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
