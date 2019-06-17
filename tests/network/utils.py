import contextlib
import ipaddress
import logging

from pytest_testconfig import config as py_config

from resources.network_attachment_definition import BridgeNetworkAttachmentDefinition
from utilities.utils import generate_yaml_from_template
from utilities import console

LOGGER = logging.getLogger(__name__)


def generate_network_cr_from_template(name, namespace, bridge=None, cni=None, vlan=None):
    """
    Generate network CR from template (Jinja)

    Args:
        name (str): Network name.
        namespace (str): Namespace where to create the network CR.
        bridge (str): Bridge name.
        cni (str): cni name. (cnv-bridge, bridge, ovs etc..)
        vlan (str): VLAN id.

    Returns:
        dict: Generated dict from the template.
    """
    file_ = "tests/manifests/network/network-cr-template.yml"
    template_params = {
        'name': name,
        'namespace': namespace,
        'bridge': bridge or name,
        'cni': cni or 'cnv-bridge',
        'vlan': f'"vlan": {vlan},' if vlan else ''
    }
    return generate_yaml_from_template(file_=file_, **template_params)


@contextlib.contextmanager
def _bridge(pod, name):
    LOGGER.info(f"Adding bridge {name} using {pod.name}")
    pod.execute(
        command=["ip", "link", "add", name, "type", "bridge"],
        container=pod.containers()[0].name
    )
    try:
        yield
    finally:
        LOGGER.info(f"Deleting bridge {name} using {pod.name}")
        pod.execute(
            command=["ip", "link", "del", name],
            container=pod.containers()[0].name
        )


class Bridge:
    def __init__(self, name, worker_pods):
        self.name = name
        self._worker_pods = worker_pods
        self._stack = None

    def __enter__(self):
        # use ExitStack to guarantee cleanup even when some workers fail
        with contextlib.ExitStack() as stack:
            for pod in self._worker_pods:
                stack.enter_context(_bridge(pod, self.name))
            self._stack = stack.pop_all()
        return self

    def __exit__(self, *args):
        if self._stack is not None:
            self._stack.__exit__(*args)


@contextlib.contextmanager
def bridge_nad(namespace, name, bridge, vlan=None):
    cni_type = py_config['template_defaults']['bridge_cni_name']
    with BridgeNetworkAttachmentDefinition(
            namespace=namespace.name,
            name=name,
            bridge_name=bridge,
            cni_type=cni_type,
            vlan=vlan) as nad:
        yield nad


@contextlib.contextmanager
def _vxlan(pod, name, vxlan_id, interface_name, dst_port, master_bridge):
    # group 226.100.100.100 is part of RESERVED (225.0.0.0-231.255.255.255) range and applications can not use it
    # Usage of this group eliminates the risk of overlap
    create_vxlan_cmd = ["ip", "link", "add", name, "type", "vxlan", "id", vxlan_id,
                        "group", "226.100.100.100", "dev", interface_name, "dstport", dst_port]
    # vid(vlan id) 1-4094 allows all vlan range to forward traffic via vxlan tunnel. It makes tunnel generic
    config_vxlan_cmd = [
        ["ip", "link", "set", name, "master", master_bridge],
        ["bridge", "vlan", "add", "dev", name, "vid", "1-4094"],
        ["ip", "link", "set", "up", name]
    ]

    LOGGER.info(f"Adding vxlan {name} using {pod.name}")
    pod.execute(command=create_vxlan_cmd, container=pod.containers()[0].name)
    try:
        for cmd in config_vxlan_cmd:
            pod.execute(command=cmd, container=pod.containers()[0].name)
        yield
    finally:
        LOGGER.info(f"Deleting vxlan {name} using {pod.name}")
        pod.execute(command=["ip", "link", "del", name], container=pod.containers()[0].name)


class VXLANTunnel:
    # destination port 4790 parameter can be any free port in order to avoid overlap with the existing applications
    def __init__(self, name, vxlan_id, master_bridge, worker_pods, interface_name='eth0', dst_port="4790"):
        self.name = name
        self.vxlan_id = vxlan_id
        self.master_bridge = master_bridge
        self.interface_name = interface_name
        self.dst_port = dst_port
        self._worker_pods = worker_pods
        self._stack = None

    def __enter__(self):
        # use ExitStack to guarantee cleanup even when some nodes fail to
        # create the vxlan
        with contextlib.ExitStack() as stack:
            for pod in self._worker_pods:
                stack.enter_context(_vxlan(
                    pod=pod,
                    name=self.name,
                    vxlan_id=self.vxlan_id,
                    interface_name=self.interface_name,
                    dst_port=self.dst_port,
                    master_bridge=self.master_bridge)
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


def get_vmi_ip_by_name(vmi, name):
    for iface in vmi.interfaces:
        if iface.name == name:
            return ipaddress.ip_interface(iface.ipAddress).ip

    raise IpNotFound(name)


def run_test_connectivity(src_vm, dst_vm, dst_ip, positive, namespace):
    """
    Check connectivity
    """
    expected = ' 0% packet loss' if positive else '100% packet loss'
    LOGGER.info(
        f"{'Positive' if positive else 'Negative'}: Ping {dst_ip} from {src_vm} to {dst_vm}"
    )
    with console.Fedora(vm=src_vm, namespace=namespace) as src_vm_console:
        src_vm_console.sendline(f'ping -w 3 {dst_ip}')
        src_vm_console.expect(expected)
