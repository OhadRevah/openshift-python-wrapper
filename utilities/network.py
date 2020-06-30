import contextlib
import ipaddress
import json
import logging

from openshift.dynamic.exceptions import ConflictError
from pytest_testconfig import config as py_config
from resources.network_attachment_definition import NetworkAttachmentDefinition
from resources.node_network_configuration_policy import NodeNetworkConfigurationPolicy
from resources.node_network_state import NodeNetworkState
from resources.resource import sub_resource_level
from resources.utils import TimeoutExpiredError, TimeoutSampler


LOGGER = logging.getLogger(__name__)
IFACE_UP_STATE = NodeNetworkConfigurationPolicy.Interface.State.UP
IFACE_ABSENT_STATE = NodeNetworkConfigurationPolicy.Interface.State.ABSENT
LINUX_BRIDGE = "linux-bridge"
OVS = "ovs"


class VXLANTunnelNNCP(NodeNetworkConfigurationPolicy):
    def __init__(
        self,
        name,
        vxlan_name,
        vxlan_id,
        base_interface,
        worker_pods,
        dst_port=4790,
        remote="226.100.100.100",
        node_selector=None,
        teardown=True,
    ):
        super().__init__(
            name=name,
            worker_pods=worker_pods,
            node_selector=node_selector,
            teardown=teardown,
        )
        self.vxlan_name = vxlan_name
        self.vxlan_id = vxlan_id
        self.base_interface = base_interface
        self.dst_port = dst_port
        self.remote = remote

    def __enter__(self):
        super().__enter__()

        try:
            self.validate_create()
            return self
        except Exception as e:
            LOGGER.error(e)
            self.clean_up()
            raise

    def __exit__(self, exception_type, exception_value, traceback):
        if not self.teardown:
            return
        self.clean_up()

    def to_dict(self):
        res = super().to_dict()
        res["spec"]["desiredState"]["interfaces"] = [
            {
                "name": self.vxlan_name,
                "type": "vxlan",
                "state": IFACE_UP_STATE,
                "vxlan": {
                    "id": self.vxlan_id,
                    "base-iface": self.base_interface,
                    "remote": self.remote,
                    "destination-port": self.dst_port,
                },
            }
        ]
        return res

    def clean_up(self):
        try:
            self._absent_vxlan()
            self.wait_for_vxlan_deleted()
        except TimeoutExpiredError as e:
            LOGGER.error(e)

        self.delete()

    def validate_create(self):
        for pod in self.worker_pods:
            node_network_state = NodeNetworkState(name=pod.node.name)
            node_network_state.wait_until_up(name=self.vxlan_name)

    def _absent_vxlan(self):
        res = self.to_dict()
        res["spec"]["desiredState"]["interfaces"][0]["state"] = IFACE_ABSENT_STATE
        samples = TimeoutSampler(
            timeout=3,
            sleep=1,
            exceptions=ConflictError,
            func=self.update,
            resource_dict=res,
        )
        for _ in samples:
            return

    def wait_for_vxlan_deleted(self):
        for pod in self.worker_pods:
            node_network_state = NodeNetworkState(name=pod.node.name)
            node_network_state.wait_until_deleted(name=self.vxlan_name)


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
        ipv4_dhcp=None,
        teardown=True,
        ipv6_enable=False,
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
        super().__init__(
            name=name,
            worker_pods=worker_pods,
            node_selector=node_selector,
            teardown=teardown,
            mtu=mtu,
            ports=ports,
            ipv4_dhcp=ipv4_dhcp,
            ipv6_enable=ipv6_enable,
        )
        self.bridge_name = bridge_name
        self.bridge_type = bridge_type
        self.stp_config = stp_config

    def to_dict(self):
        # At the first time, it creates the dict.
        # When calling update, the caller updates the dict and this function
        # will not init it anymore
        if not self.iface:
            bridge_ports = [{"name": port} for port in self.ports]
            self.iface = {
                "name": self.bridge_name,
                "type": self.bridge_type,
                "state": IFACE_UP_STATE,
                "bridge": {"options": {"stp": self.stp_config}, "port": bridge_ports},
            }
            if self.mtu:
                self.iface["mtu"] = self.mtu
                for port in bridge_ports:
                    _port = {
                        "name": port["name"],
                        "type": "ethernet",
                        "state": IFACE_UP_STATE,
                        "mtu": self.mtu,
                    }
                    self.set_interface(interface=_port)

        res = super().to_dict()
        return res


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
        teardown=True,
    ):
        super().__init__(
            name=name,
            worker_pods=worker_pods,
            bridge_name=bridge_name,
            bridge_type="linux-bridge",
            stp_config={"enabled": stp_config},
            ports=ports,
            mtu=mtu,
            node_selector=node_selector,
            ipv4_dhcp=ipv4_dhcp,
            teardown=teardown,
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
        teardown=True,
    ):
        super().__init__(
            name=name,
            worker_pods=worker_pods,
            bridge_name=bridge_name,
            bridge_type="ovs-bridge",
            stp_config=stp_config,
            ports=ports,
            mtu=mtu,
            node_selector=node_selector,
            ipv4_dhcp=ipv4_dhcp,
            teardown=teardown,
        )

    def to_dict(self):
        res = super().to_dict()

        if not self.ports:
            # If no ports were specified - should add:
            # 1. an internal port entry
            # 2. an interface entry (of type "ovs-interface")
            ovs_iface_name = "ovs"
            for idx, iface in enumerate(res["spec"]["desiredState"]["interfaces"]):
                ovs_iface_name = f"{ovs_iface_name}{idx}"
                if iface["type"] == "ovs-bridge":
                    iface["bridge"]["port"].append({"name": ovs_iface_name})
                    self.ports = {"name": ovs_iface_name}
                    break

            ovs_iface = {
                "name": ovs_iface_name,
                "type": "ovs-interface",
                "state": IFACE_UP_STATE,
            }
            res["spec"]["desiredState"]["interfaces"].append(ovs_iface)
            self.ifaces.append(ovs_iface)

        return res


class VLANInterfaceNodeNetworkConfigurationPolicy(NodeNetworkConfigurationPolicy):
    def __init__(
        self,
        worker_pods,
        iface_state,
        base_iface,
        tag,
        name=None,
        node_selector=None,
        ipv4_dhcp=None,
        teardown=True,
        ipv6_enable=False,
    ):
        iface_name = f"{base_iface}.{tag}"
        if not name:
            name = f"{iface_name}-nncp"

        super().__init__(
            name=name,
            node_selector=node_selector,
            worker_pods=worker_pods,
            teardown=teardown,
            ipv4_dhcp=ipv4_dhcp,
            ipv6_enable=ipv6_enable,
        )
        self.iface_state = iface_state
        self.base_iface = base_iface
        self.tag = tag
        self.iface_name = iface_name
        self.iface = None

    def to_dict(self):
        if not self.iface:
            self.iface = {
                "name": self.iface_name,
                "type": "vlan",
                "state": self.iface_state,
            }
        vlan_spec = {"vlan": {"base-iface": self.base_iface, "id": self.tag}}
        self.iface.update(vlan_spec)
        res = super().to_dict()

        return res


class BridgeNetworkAttachmentDefinition(NetworkAttachmentDefinition):
    def __init__(
        self,
        name,
        namespace,
        bridge_name,
        cni_type,
        vlan=None,
        client=None,
        mtu=None,
        teardown=True,
    ):
        super().__init__(
            name=name, namespace=namespace, client=client, teardown=teardown
        )

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

        self.bridge_name = bridge_name
        self.cni_type = cni_type
        self.vlan = vlan
        self.mtu = mtu

    def to_dict(self):
        res = super().to_dict()
        spec_config = {"cniVersion": "0.3.1", "name": self.bridge_name}
        bridge_dict = {"type": self.cni_type, "bridge": self.bridge_name}
        if self.mtu:
            bridge_dict["mtu"] = self.mtu
        if self.vlan:
            bridge_dict["vlan"] = self.vlan
        spec_config["plugins"] = [bridge_dict]

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
        teardown=True,
    ):
        super().__init__(
            name=name,
            namespace=namespace,
            bridge_name=bridge_name,
            cni_type=cni_type,
            vlan=vlan,
            client=client,
            mtu=mtu,
            teardown=teardown,
        )
        self.tuning_type = tuning_type

    def to_dict(self):
        res = super().to_dict()
        config_plugins = res["spec"]["config"]["plugins"]

        if self.tuning_type:
            tuning_dict = {"type": self.tuning_type}

            config_plugins.append(tuning_dict)

        res["spec"]["config"] = json.dumps(res["spec"]["config"])
        return res

    @property
    def resource_name(self):
        return f"bridge.network.kubevirt.io/{self.bridge_name}"


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
        teardown=True,
    ):
        super().__init__(
            name=name,
            namespace=namespace,
            bridge_name=bridge_name,
            cni_type=cni_type,
            vlan=vlan,
            client=client,
            mtu=mtu,
            teardown=teardown,
        )

    def to_dict(self):
        res = super().to_dict()
        res["spec"]["config"] = json.dumps(res["spec"]["config"])
        return res

    @property
    def resource_name(self):
        return f"ovs-cni.network.kubevirt.io/{self.bridge_name}"


class BondNodeNetworkConfigurationPolicy(NodeNetworkConfigurationPolicy):
    def __init__(
        self,
        name,
        bond_name,
        slaves,
        worker_pods,
        mode,
        node_selector=None,
        mtu=None,
        teardown=True,
        ipv4_dhcp=False,
        ipv6_enable=False,
    ):
        super().__init__(
            name=name,
            worker_pods=worker_pods,
            node_selector=node_selector,
            teardown=teardown,
            mtu=mtu,
            ipv4_dhcp=ipv4_dhcp,
            ipv6_enable=ipv6_enable,
        )
        self.bond_name = bond_name
        self.slaves = slaves
        self.mode = mode
        self.ports = self.slaves

    def to_dict(self):
        if not self.iface:
            self.iface = {
                "name": self.bond_name,
                "type": "bond",
                "state": NodeNetworkConfigurationPolicy.Interface.State.UP,
                "mtu": self.mtu,
                "link-aggregation": {
                    "mode": self.mode,
                    "slaves": self.slaves,
                    "options": {"miimon": "120"},
                },
            }
            if self.mtu:
                for port in self.ports:
                    _port = {
                        "name": port,
                        "type": "ethernet",
                        "state": NodeNetworkConfigurationPolicy.Interface.State.UP,
                        "mtu": self.mtu,
                    }
                    self.set_interface(interface=_port)

        res = super().to_dict()
        return res


BRIDGE_DEVICE_TYPE = {
    LINUX_BRIDGE: LinuxBridgeNodeNetworkConfigurationPolicy,
    OVS: OvsBridgeNodeNetworkConfigurationPolicy,
}
BRIDGE_NAD_TYPE = {
    LINUX_BRIDGE: LinuxBridgeNetworkAttachmentDefinition,
    OVS: OvsBridgeNetworkAttachmentDefinition,
}


def get_vmi_ip_v4_by_name(vmi, name):
    sampler = TimeoutSampler(timeout=120, sleep=1, func=lambda: vmi.interfaces)
    try:
        for sample in sampler:
            for iface in sample:
                if iface.name == name:
                    for ipaddr in iface.ipAddresses:
                        try:
                            ip = ipaddress.ip_interface(address=ipaddr)
                            if ip.version == 4:
                                return ip.ip
                        # ipaddress module fails to identify IPv6 with % as a valid IP
                        except ValueError as e:
                            if (
                                "does not appear to be an IPv4 or IPv6 "
                                "interface" in str(e)
                            ):
                                continue
    except TimeoutExpiredError:
        raise IpNotFound(name)


class IpNotFound(Exception):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"IP address not found for interface {self.name}"


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


class EthernetNetworkConfigurationPolicy(NodeNetworkConfigurationPolicy):
    def __init__(
        self,
        name,
        interfaces_name,
        worker_pods,
        iface_state=NodeNetworkConfigurationPolicy.Interface.State.UP,
        node_selector=None,
        teardown=True,
        ipv4_dhcp=None,
        node_active_nics=None,
    ):
        super().__init__(
            name=name,
            worker_pods=worker_pods,
            node_selector=node_selector,
            ipv4_dhcp=ipv4_dhcp,
            teardown=teardown,
            node_active_nics=node_active_nics,
        )
        self.interfaces_name = interfaces_name
        self.iface_state = iface_state

    def to_dict(self):
        res = None
        if not self.interfaces_name:
            raise ValueError("Value of interface_name cannot be empty")
        for nic in self.interfaces_name:
            self.iface = {
                "name": nic,
                "type": "ethernet",
                "state": self.iface_state,
            }
            if self.ipv4_dhcp is not None:
                self.iface["ipv4"] = {"dhcp": self.ipv4_dhcp, "enabled": self.ipv4_dhcp}
            self.set_interface(interface=self.iface)
            res = super().to_dict()
        return res


def get_hosts_common_ports(nodes_active_nics):
    """
    Get list of common ports from nodes_active_nics.

    nodes_active_nics like
    [['ens3', 'ens4', 'ens6', 'ens5'],
    ['ens3', 'ens8', 'ens6', 'ens7'],
    ['ens3', 'ens8', 'ens6', 'ens7']]

    will return ['ens3', 'ens6']
    """
    # Exclude primary NIC from the set (nics[1:])
    nics_list = [nics[1:] for nics in nodes_active_nics.values()]
    nics_list = list(set.intersection(*[set(list) for list in nics_list]))

    # Insert the primary NIC to be the first in the list
    nics_list.insert(0, nodes_active_nics[[*nodes_active_nics][0]][0])

    LOGGER.info(f"Hosts common NICs: {nics_list}")
    return nics_list
