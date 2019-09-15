import contextlib
import ipaddress
import logging
import re

from pytest_testconfig import config as py_config
from resources.network_attachment_definition import (
    LinuxBridgeNetworkAttachmentDefinition,
)
from utilities import console


LOGGER = logging.getLogger(__name__)


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


class IpNotFound(Exception):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"IP address not found for interface {self.name}"


def get_vmi_ip_v4_by_name(vmi, name):
    for iface in vmi.interfaces:
        if iface.name == name:
            for ipaddr in iface.ipAddresses:
                ip = ipaddress.ip_interface(ipaddr)
                if ip.version == 4:
                    return ip.ip

    raise IpNotFound(name)


def _console_ping(src_vm, dst_ip, mtu=None):
    ping_cmd = f"ping -w 3 {dst_ip}"
    if mtu:
        ping_cmd += f" -s {mtu} -M do"
    with console.Fedora(vm=src_vm) as src_vm_console:
        src_vm_console.sendline(ping_cmd)
        while True:
            line = src_vm_console.readline()
            m = re.search(b"([0-9]+)% packet loss, ", line)
            if m is not None:
                LOGGER.info(f"ping returned {m.string.strip()}")
                return m.groups()


def assert_ping_successful(src_vm, dst_ip, mtu=None):
    assert _console_ping(src_vm, dst_ip, mtu)[0] == b"0"


def assert_no_ping(src_vm, dst_ip, mtu=None):
    assert _console_ping(src_vm, dst_ip, mtu)[0] == b"100"


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
