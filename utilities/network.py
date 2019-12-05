import contextlib
import json
import logging

from resources.network_attachment_definition import NetworkAttachmentDefinition
from resources.node_network_configuration_policy import NodeNetworkConfigurationPolicy
from resources.node_network_state import NodeNetworkState
from resources.resource import sub_resource_level
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


class BridgeNodeNetworkConfigurationPolicy(NodeNetworkConfigurationPolicy):
    def __init__(
        self,
        name,
        worker_pods,
        bridge_name,
        bridge_type,
        stp_config,
        ports=None,
        mtu=None,
        node_selector=None,
        ipv4_dhcp=False,
    ):
        """
        Create bridge on nodes (according node_selector, all if no selector presents)

        Args:
            name (str): Policy name.
            worker_pods (list): List of Pods instances.
            bridge_name (str): Bridge name.
            bridge_type (str): Bridge type (Linux Bridge, OVS)
            stp_config (bool): Spanning Tree enabled/disabled.
            ports (list): The bridge's slave port(s).
            mtu (int): MTU size
            ipv4_dhcp: determines if ipv4_dhcp should be used
        """
        super().__init__(name=name)
        self._worker_pods = worker_pods
        self.bridge_name = bridge_name
        self.bridge_type = bridge_type
        self.stp_config = stp_config
        self.ports = ports or []
        self.mtu = mtu
        self.bridge = None
        self.node_selector = node_selector
        self._ipv4_dhcp = ipv4_dhcp
        self.mtu_dict = {}
        self.ipv4_iface_state = {}
        if self.node_selector:
            for pod in self._worker_pods:
                if pod.node.name == self.node_selector:
                    self._worker_pods = [pod]
                    break

    def _to_dict(self):
        # At the first time, it creates the dict.
        # When calling update, the caller updates the dict and this function
        # will not init it anymore
        if not self.bridge:
            bridge_ports = [{"name": port} for port in self.ports]
            self.bridge = {
                "name": self.bridge_name,
                "type": self.bridge_type,
                "state": "up",
                "bridge": {"options": {"stp": self.stp_config}, "port": bridge_ports},
            }

        if self._ipv4_dhcp:
            self.bridge["ipv4"] = {"dhcp": True, "enabled": True}

        self.set_interface(self.bridge)
        res = super()._to_dict()

        return res

    def __enter__(self):
        if self._ipv4_dhcp:
            self._ipv4_state_backup()

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

    @property
    def ipv4_dhcp(self):
        return self._ipv4_dhcp

    @ipv4_dhcp.setter
    def ipv4_dhcp(self, ipv4_dhcp):
        if ipv4_dhcp != self._ipv4_dhcp:
            self._ipv4_dhcp = ipv4_dhcp

            if self._ipv4_dhcp:
                self._ipv4_state_backup()
                self.bridge["ipv4"] = {"dhcp": True, "enabled": True}

            self.set_interface(self.bridge)
            self.apply()

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
            node_network_state = NodeNetworkState(name=pod.node.name)
            node_network_state.wait_until_deleted(self.bridge_name)

    def validate_create(self):
        for pod in self._worker_pods:
            node_network_state = NodeNetworkState(name=pod.node.name)
            node_network_state.wait_until_up(self.bridge_name)

    def _ipv4_state_backup(self):
        # Backup current state of dhcp for the interfaces which arent veth or current bridge
        for pod in self._worker_pods:
            if (
                self.node_selector
                and self.node_selector["kubernetes.io/hostname"] != pod.node.name
            ):
                continue
            node_network_state = NodeNetworkState(name=pod.node.name)
            self.ipv4_iface_state[pod.node.name] = {}
            for interface in node_network_state.instance.status.currentState.interfaces:
                if interface["name"] in self.ports:
                    self.ipv4_iface_state[pod.node.name].update(
                        {
                            interface["name"]: {
                                k: interface["ipv4"][k] for k in ("dhcp", "enabled")
                            }
                        }
                    )

    def _absent_interface(self):
        self.bridge["state"] = "absent"
        self.set_interface(self.bridge)

        if self._ipv4_dhcp:
            previous_state = None
            temp_ipv4_iface_state = {}
            for pod in self._worker_pods:
                if self.node_selector:
                    # Assume node selector is of type hostname
                    if self.node_selector["kubernetes.io/hostname"] != pod.node.name:
                        continue
                    previous_state = temp_ipv4_iface_state[
                        self.node_selector["kubernetes.io/hostname"]
                    ]
                node_network_state = NodeNetworkState(name=pod.node.name)
                temp_ipv4_iface_state[pod.node.name] = {}
                # Find which interfaces got changed (of those that are connected to bridge)
                for (
                    interface
                ) in node_network_state.instance.status.currentState.interfaces:
                    if interface["name"] in self.ports:
                        x = {k: interface["ipv4"][k] for k in ("dhcp", "enabled")}
                        if self.ipv4_iface_state[pod.node.name][interface["name"]] != x:
                            temp_ipv4_iface_state[pod.node.name].update(
                                {
                                    interface["name"]: self.ipv4_iface_state[
                                        pod.node.name
                                    ][interface["name"]]
                                }
                            )

            # Assuming all nodes have same interfaces, and that if node selector exists it is from type hostname
            if previous_state is None:
                previous_state = next(iter(temp_ipv4_iface_state.values()))

            # Restore DHCP state of the changed bridge connected ports
            for iface_name, ipv4 in previous_state.items():
                interface = {"name": iface_name, "ipv4": ipv4}
                self.set_interface(interface)

        self.apply()


class LinuxBridgeNodeNetworkConfigurationPolicy(BridgeNodeNetworkConfigurationPolicy):
    def __init__(
        self,
        name,
        worker_pods,
        bridge_name,
        stp_config=False,
        ports=None,
        mtu=None,
        node_selector=None,
        ipv4_dhcp=None,
    ):
        super().__init__(
            name,
            worker_pods,
            bridge_name,
            bridge_type="linux-bridge",
            stp_config={"enabled": stp_config},
            ports=ports,
            mtu=mtu,
            node_selector=node_selector,
            ipv4_dhcp=ipv4_dhcp,
        )


class OvsBridgeNodeNetworkConfigurationPolicy(BridgeNodeNetworkConfigurationPolicy):
    def __init__(
        self,
        name,
        worker_pods,
        bridge_name,
        ports,
        stp_config=True,
        mtu=None,
        node_selector=None,
        ipv4_dhcp=None,
    ):
        super().__init__(
            name,
            worker_pods,
            bridge_name,
            bridge_type="ovs-bridge",
            stp_config=stp_config,
            ports=ports,
            mtu=mtu,
            node_selector=node_selector,
            ipv4_dhcp=ipv4_dhcp,
        )

    def _to_dict(self):
        res = super()._to_dict()

        if not self.ports:
            # If no ports were specified - should add:
            # 1. an internal port entry
            # 2. an interface entry (of type "ovs-interface")
            ovs_iface_name = "ovs"
            for idx, iface in enumerate(res["spec"]["desiredState"]["interfaces"]):
                ovs_iface_name = f"{ovs_iface_name}{idx}"
                if iface["type"] == "ovs-bridge":
                    iface["bridge"]["port"].append({"name": ovs_iface_name})
                    break

            ovs_iface = {"name": ovs_iface_name, "type": "ovs-interface", "state": "up"}
            res["spec"]["desiredState"]["interfaces"].append(ovs_iface)

        return res


class BridgeNetworkAttachmentDefinition(NetworkAttachmentDefinition):
    def __init__(
        self, name, namespace, bridge_name, cni_type, vlan=None, client=None, mtu=None
    ):
        super().__init__(name=name, namespace=namespace, client=client)

        # An object must not be created as type BridgeNetworkAttachmentDefinition, but only as one of its successors.
        sub_lvl = sub_resource_level(
            current_class=self.__class__,
            owner_class=BridgeNetworkAttachmentDefinition,
            parent_class=NetworkAttachmentDefinition,
        )
        if sub_lvl is None:
            raise TypeError(
                f"Cannot create an object of type {self.__class__}.\n"
                "Only its sub-types LinuxBridgeNetworkAttachmentDefinition and "
                "OvsBridgeNetworkAttachmentDefinition are allowed."
            )

        self._bridge_name = bridge_name
        self._cni_type = cni_type
        self._vlan = vlan
        self._mtu = mtu

    def _to_dict(self):
        res = super()._to_dict()
        spec_config = {"cniVersion": "0.3.1", "name": self._bridge_name}
        bridge_dict = {"type": self._cni_type, "bridge": self._bridge_name}
        spec_config["plugins"] = [bridge_dict]
        if self._vlan:
            spec_config["vlan"] = self._vlan

        res["spec"]["config"] = spec_config
        return res


class LinuxBridgeNetworkAttachmentDefinition(BridgeNetworkAttachmentDefinition):
    def __init__(
        self,
        name,
        namespace,
        bridge_name,
        cni_type="cnv-bridge",
        vlan=None,
        client=None,
        mtu=None,
        tuning_type=None,
    ):
        super().__init__(name, namespace, bridge_name, cni_type, vlan, client, mtu)
        self._tuning_type = tuning_type

    def _to_dict(self):
        res = super()._to_dict()
        config_plugins = res["spec"]["config"]["plugins"]

        if self._tuning_type:
            tuning_dict = {"type": self._tuning_type}
            if self._mtu:
                tuning_dict["mtu"] = self._mtu

            config_plugins.append(tuning_dict)

        res["spec"]["config"] = json.dumps(res["spec"]["config"])
        return res

    @property
    def resource_name(self):
        return f"bridge.network.kubevirt.io/{self._bridge_name}"


class OvsBridgeNetworkAttachmentDefinition(BridgeNetworkAttachmentDefinition):
    def __init__(
        self,
        name,
        namespace,
        bridge_name,
        cni_type="ovs",
        vlan=None,
        client=None,
        mtu=None,
    ):
        super().__init__(name, namespace, bridge_name, cni_type, vlan, client, mtu)

    def _to_dict(self):
        res = super()._to_dict()
        res["spec"]["config"] = json.dumps(res["spec"]["config"])
        return res

    @property
    def resource_name(self):
        return f"ovs-cni.network.kubevirt.io/{self._bridge_name}"


class OvsBridgeOverVxlan(object):
    def __init__(self, bridge_name, vxlan_iface_name, ovs_worker_pods, remote_ips):
        self.bridge_name = bridge_name
        self.vxlan_iface_name = vxlan_iface_name
        self.ovs_worker_pods = ovs_worker_pods
        self.remote_ips = remote_ips
        self.successfully_bridged_pods = []

    def __enter__(self):
        self.setup_ovs_br()
        return self

    def __exit__(self, excpt_type, excpt_value, excpt_traceback):
        self.clean_up_ovs_br()

    def setup_ovs_br(self):
        LOGGER.info(
            f"Creating OVS bridge {self.bridge_name} over new VXLAN interface {self.vxlan_iface_name}."
        )

        br_idx = 0
        base_port = 4795
        for pod in self.ovs_worker_pods:
            pod.execute(command=["ovs-vsctl", "add-br", self.bridge_name])
            self.successfully_bridged_pods.append(pod)

            ovs_br_cmds = []
            idx = 0
            for node_name, node_ip in self.remote_ips.items():
                if node_name != pod.node.name:
                    iface_name = f"{self.vxlan_iface_name}{idx}"
                    ovs_br_cmds.append(
                        [
                            "ovs-vsctl",
                            "add-port",
                            self.bridge_name,
                            iface_name,  # OVS port name
                            "--",
                            "set",
                            "Interface",
                            iface_name,  # VXLAN interface name
                            "type=vxlan",
                            f"options:remote_ip={node_ip}",
                            f"options:dst_port={base_port + idx}",
                        ]
                    )
                    idx += 1

            ovs_br_cmds.append(["ip", "link", "set", "up", f"{self.bridge_name}"])

            for cmd in ovs_br_cmds:
                pod.execute(command=cmd)

            br_idx += 1

    def clean_up_ovs_br(self):
        LOGGER.info(
            f"Removing OVS bridge {self.bridge_name} with its new VXLAN interface {self.vxlan_iface_name}."
        )
        for bridge_pod in self.successfully_bridged_pods:
            bridge_pod.execute(["ovs-vsctl", "del-br", self.bridge_name])
        self.successfully_bridged_pods.clear()
