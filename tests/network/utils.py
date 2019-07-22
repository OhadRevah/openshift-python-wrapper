import contextlib
import ipaddress
import logging
import re

import pexpect
from pytest_testconfig import config as py_config

from resources.network_attachment_definition import BridgeNetworkAttachmentDefinition

from tests.network.nmstate import linux_bridge

from utilities import console

LOGGER = logging.getLogger(__name__)


class CommandExecFailed(Exception):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"Command: {self.name} - exec failed."


@contextlib.contextmanager
def _bridge(pod, name, nic, mtu, disable_vlan_filtering):
    def _set_mtu(iface, mtu):
        return ["ip", "link", "set", iface, "mtu", mtu]

    iface_mtu = None
    try:
        LOGGER.info(f"Adding bridge {name} to {pod.node.name} using nmstate")
        linux_bridge.create(pod.node.name, name, nic)

        # This is a temporal measure there are some tests where we need
        # trunk but that will be fixed at future versions of CNI linux-bridge [1]
        # [1] https://jira.coreos.com/browse/CNV-1804
        if disable_vlan_filtering:
            pod.execute(
                [
                    "ip",
                    "link",
                    "set",
                    "dev",
                    name,
                    "type",
                    "bridge",
                    "vlan_filtering",
                    "0",
                ]
            )

        if mtu:
            iface_mtu = pod.execute(
                command=["cat", f"/sys/class/net/{nic}/mtu"]
            ).strip()
            pod.execute(command=_set_mtu(name, mtu))

        if nic is not None:
            if mtu:
                pod.execute(command=_set_mtu(nic, mtu))
        yield
    finally:
        if nic is not None and mtu and iface_mtu:
            pod.execute(command=_set_mtu(nic, iface_mtu))

        LOGGER.info(f"Deleting bridge {name} at {pod.node.name} using nmstate")
        linux_bridge.delete(pod.node.name, name)


class Bridge:
    def __init__(
        self,
        name,
        worker_pods,
        nic=None,
        nodes_nics=None,
        master_index=None,
        mtu=None,
        disable_vlan_filtering=False,
    ):
        """
        Create bridge on all nodes (Using privileged pods)

        Args:
            name (str): Bridge name.
            worker_pods (list): List of Pods instances.
            nic (str): The bridge's slave nic, exclusive with nodes_nics and master_index.
            nodes_nics (dict): Dict of {nodes: [NICs]}. get it from 'nodes_active_nics' fixture, exclusive with nic.
            master_index (int): The index on the NIC to use, exclusive with nic.
            mtu (int): MTU size
            disable_vlan_filtering: no vlan_filtering configured at node bridges
        """
        self.name = name
        self._worker_pods = worker_pods
        self.nic = nic
        self.master_index = master_index
        self.nodes_nics = nodes_nics
        self.mtu = mtu
        self.disable_vlan_filtering = disable_vlan_filtering
        self._stack = None

    def __enter__(self):
        # use ExitStack to guarantee cleanup even when some workers fail
        with contextlib.ExitStack() as stack:
            for pod in self._worker_pods:
                nic_to_bridge = None
                if self.nic:
                    nic_to_bridge = self.nic
                elif self.nodes_nics and self.master_index is not None:
                    nic_to_bridge = self.nodes_nics[pod.node.name][self.master_index]
                stack.enter_context(
                    _bridge(
                        pod,
                        self.name,
                        nic_to_bridge,
                        self.mtu,
                        self.disable_vlan_filtering,
                    )
                )
            self._stack = stack.pop_all()
        return self

    def __exit__(self, *args):
        if self._stack is not None:
            self._stack.__exit__(*args)


@contextlib.contextmanager
def bridge_nad(namespace, name, bridge, vlan=None, tuning=None, mtu=None):
    cni_type = py_config["template_defaults"]["bridge_cni_name"]
    tuning_type = (
        py_config["template_defaults"]["bridge_tuning_name"] if tuning else None
    )
    with BridgeNetworkAttachmentDefinition(
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
def _vxlan(pod, name, vxlan_id, interface_name, dst_port, master_bridge):
    # group 226.100.100.100 is part of RESERVED (225.0.0.0-231.255.255.255) range and applications can not use it
    # Usage of this group eliminates the risk of overlap
    create_vxlan_cmd = [
        "ip",
        "link",
        "add",
        name,
        "type",
        "vxlan",
        "id",
        vxlan_id,
        "group",
        "226.100.100.100",
        "dev",
        interface_name,
        "dstport",
        dst_port,
    ]
    # vid(vlan id) 1-4094 allows all vlan range to forward traffic via vxlan tunnel. It makes tunnel generic
    config_vxlan_cmd = [
        ["ip", "link", "set", name, "master", master_bridge],
        ["bridge", "vlan", "add", "dev", name, "vid", "1-4094"],
        ["ip", "link", "set", "up", name],
    ]

    LOGGER.info(f"Adding vxlan {name} using {pod.name}")
    pod.execute(command=create_vxlan_cmd)
    try:
        for cmd in config_vxlan_cmd:
            pod.execute(command=cmd)
        yield
    finally:
        LOGGER.info(f"Deleting vxlan {name} using {pod.name}")
        pod.execute(command=["ip", "link", "del", name])


class VXLANTunnel:
    # destination port 4790 parameter can be any free port in order to avoid overlap with the existing applications
    def __init__(
        self, name, vxlan_id, master_bridge, worker_pods, nodes_nics, dst_port="4790"
    ):
        self.name = name
        self.vxlan_id = vxlan_id
        self.master_bridge = master_bridge
        self.nodes_nics = nodes_nics
        self.dst_port = dst_port
        self._worker_pods = worker_pods
        self._stack = None

    def __enter__(self):
        # use ExitStack to guarantee cleanup even when some nodes fail to
        # create the vxlan
        with contextlib.ExitStack() as stack:
            for pod in self._worker_pods:
                stack.enter_context(
                    _vxlan(
                        pod=pod,
                        name=self.name,
                        vxlan_id=self.vxlan_id,
                        interface_name=self.nodes_nics[pod.node.name][0],
                        dst_port=self.dst_port,
                        master_bridge=self.master_bridge,
                    )
                )
            self._stack = stack.pop_all()
        return self

    def __exit__(self, *args):
        if self._stack is not None:
            self._stack.__exit__(*args)


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


def vm_run_commands(vm, commands, timeout=60):
    """
    Run a list of commands inside VM and check all commands return 0.
    If return code other than 0 then it will break execution and raise exception.

    Args:
        vm (obj): VirtualMachine
        commands (list): List of commands
        timeout (int): Time to wait for the command output
    """
    with console.Fedora(vm=vm) as vmc:
        for command in commands:
            LOGGER.info(f"Execute {command} on {vm.name}")
            vmc.sendline(command)
            vmc.sendline(
                "echo rc==$?=="
            )  # This construction rc==$?== is unique. Return code validation
            try:
                vmc.expect("rc==0==", timeout=timeout)  # Expected return code is 0
            except pexpect.exceptions.TIMEOUT:
                raise CommandExecFailed(command)
