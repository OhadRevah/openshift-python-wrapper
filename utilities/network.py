import contextlib
import logging

from resources.node_network_configuration_policy import NodeNetworkConfigurationPolicy
from resources.node_network_state import NodeNetworkState
from resources.utils import TimeoutExpiredError


LOGGER = logging.getLogger(__name__)


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


def _set_iface_mtu(pod, port, mtu):
    pod.execute(command=["ip", "link", "set", port, "mtu", mtu])


class LinuxBridgeNodeNetworkConfigurationPolicy(NodeNetworkConfigurationPolicy):
    def __init__(
        self, name, worker_pods, bridge_name, ports=None, mtu=None, node_selector=None
    ):
        """
        Create bridge on nodes (according node_selector, all if no selector presents)

        Args:
            name (str): Policy name.
            worker_pods (list): List of Pods instances.
            bridge_name (str): Bridge name.
            ports (list): The bridge's slave port(s).
            mtu (int): MTU size
        """
        super().__init__(name=name)
        self._worker_pods = worker_pods
        self.bridge_name = bridge_name
        self.ports = ports or []
        self.mtu = mtu
        self.bridge = None
        self.node_selector = node_selector
        self.mtu_dict = {}

    def _to_dict(self):
        bridge_ports = []
        for port in self.ports:
            bridge_ports.append({"name": port})

        # At the first time, it creates the dict.
        # When calling update, the caller updates the dict and this function
        # will not init it anymore
        if not self.bridge:
            self.bridge = {
                "name": self.bridge_name,
                "type": "linux-bridge",
                "state": "up",
                "bridge": {
                    "options": {"stp": {"enabled": False}},
                    "port": bridge_ports,
                },
            }

        self.set_interface(self.bridge)
        res = super()._to_dict()

        return res

    def __enter__(self):
        if self.mtu:
            for pod in self._worker_pods:
                for port in self.ports:
                    self.mtu_dict[pod.node.name + port] = pod.execute(
                        command=["cat", f"/sys/class/net/{port}/mtu"]
                    ).strip()

        super().__enter__()

        try:
            self.validate_create()
            for pod in self._worker_pods:
                if self.mtu:
                    for port in self.ports:
                        _set_iface_mtu(pod, port, self.mtu)
                    _set_iface_mtu(pod, self.bridge_name, self.mtu)
            return self
        except TimeoutExpiredError:
            self.clean_up()
            raise

    def __exit__(self, exception_type, exception_value, traceback):
        self.clean_up()

    def clean_up(self):
        if self.mtu:
            for pod in self._worker_pods:
                # Restore MTU
                for port in self.ports:
                    _set_iface_mtu(pod, port, self.mtu_dict[pod.node.name + port])

        self._absent_interface()
        self.wait_for_bridge_deleted()
        self.delete()

    def wait_for_bridge_deleted(self):
        for pod in self._worker_pods:
            LOGGER.info(
                f"validating bridge delete {self.bridge_name} - {pod.node.name}"
            )
            node_network_state = NodeNetworkState(name=pod.node.name)
            node_network_state.wait_until_deleted(self.bridge_name)

    def validate_create(self):
        for pod in self._worker_pods:
            LOGGER.info(f"validating bridge is up {self.bridge_name} - {pod.node.name}")
            node_network_state = NodeNetworkState(name=pod.node.name)
            node_network_state.wait_until_up(self.bridge_name)

    def _absent_interface(self):
        self.bridge["state"] = "absent"
        self.set_interface(self.bridge)
        self.apply()
