import contextlib
import ipaddress
import json
import logging
import random
import re
import shlex

import netaddr
from openshift.dynamic.exceptions import ConflictError
from pytest_testconfig import config as py_config
from resources.daemonset import DaemonSet
from resources.network_attachment_definition import NetworkAttachmentDefinition
from resources.node_network_configuration_policy import NodeNetworkConfigurationPolicy
from resources.node_network_state import NodeNetworkState
from resources.pod import Pod
from resources.resource import ResourceEditor, sub_resource_level
from resources.sriov_network import SriovNetwork
from resources.sriov_network_node_policy import SriovNetworkNodePolicy
from resources.utils import TimeoutExpiredError, TimeoutSampler

from utilities.constants import SRIOV
from utilities.infra import get_pod_by_name_prefix, run_ssh_commands
from utilities.virt import FEDORA_CLOUD_INIT_PASSWORD


LOGGER = logging.getLogger(__name__)
IFACE_UP_STATE = NodeNetworkConfigurationPolicy.Interface.State.UP
IFACE_ABSENT_STATE = NodeNetworkConfigurationPolicy.Interface.State.ABSENT
LINUX_BRIDGE = "linux-bridge"
OVS = "ovs"
OVS_DS_NAME = "ovs-cni-amd64"
DEPLOY_OVS = "deployOVS"


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

    def deploy(self):
        super().deploy()
        try:
            self.validate_create()
            return self
        except Exception as e:
            LOGGER.error(e)
            self.clean_up()
            raise

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
            wait_timeout=3,
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
        ipv4_enable=False,
        ipv4_dhcp=False,
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
            ipv4_enable=ipv4_enable,
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
        ipv4_enable=False,
        ipv4_dhcp=False,
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
            ipv4_enable=ipv4_enable,
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
        ipv4_enable=False,
        ipv4_dhcp=False,
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
            ipv4_enable=ipv4_enable,
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
        ipv4_enable=False,
        ipv4_dhcp=False,
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
            ipv4_enable=ipv4_enable,
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
        tuning_type="cnv-tuning",
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
        primary_slave=None,
        node_selector=None,
        mtu=None,
        teardown=True,
        ipv4_enable=False,
        ipv4_dhcp=False,
        ipv6_enable=False,
    ):
        super().__init__(
            name=name,
            worker_pods=worker_pods,
            node_selector=node_selector,
            teardown=teardown,
            mtu=mtu,
            ipv4_enable=ipv4_enable,
            ipv4_dhcp=ipv4_dhcp,
            ipv6_enable=ipv6_enable,
        )
        self.bond_name = bond_name
        self.slaves = slaves
        self.mode = mode
        self.primary_slave = primary_slave
        self.ports = self.slaves

    def to_dict(self):
        if not self.iface:
            options_dic = {"miimon": "120"}
            if self.mode == "active-backup" and self.primary_slave is not None:
                options_dic.update({"primary": self.primary_slave})

            self.iface = {
                "name": self.bond_name,
                "type": "bond",
                "state": NodeNetworkConfigurationPolicy.Interface.State.UP,
                "link-aggregation": {
                    "mode": self.mode,
                    "slaves": self.slaves,
                    "options": options_dic,
                },
            }
            if self.mtu:
                self.iface["mtu"] = self.mtu
                for port in self.ports:
                    _port = {
                        "name": port,
                        "type": "ethernet",
                        "state": NodeNetworkConfigurationPolicy.Interface.State.UP,
                        "mtu": self.mtu - 50,  # Set ports MTU lower than BOND MTU
                    }
                    self.set_interface(interface=_port)

        res = super().to_dict()
        return res


NETWORK_DEVICE_TYPE = {
    LINUX_BRIDGE: LinuxBridgeNodeNetworkConfigurationPolicy,
    OVS: OvsBridgeNodeNetworkConfigurationPolicy,
    SRIOV: SriovNetworkNodePolicy,
}
NAD_TYPE = {
    LINUX_BRIDGE: LinuxBridgeNetworkAttachmentDefinition,
    OVS: OvsBridgeNetworkAttachmentDefinition,
    SRIOV: SriovNetwork,
}


def get_vmi_ip_v4_by_name(vmi, name):
    sampler = TimeoutSampler(wait_timeout=120, sleep=1, func=lambda: vmi.interfaces)
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
                        except ValueError as error:
                            if (
                                "does not appear to be an IPv4 or IPv6 "
                                "interface" in str(error)
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
def network_nad(
    nad_type,
    nad_name,
    namespace,
    interface_name=None,
    tuning=None,
    vlan=None,
    mtu=None,
    ipam=None,
    sriov_resource_name=None,
    sriov_network_namespace=None,
):
    kwargs = {
        "name": nad_name,
        "vlan": vlan,
        "namespace": namespace.name,
    }
    if nad_type == LINUX_BRIDGE:
        kwargs["cni_type"] = py_config["linux_bridge_cni"]
        kwargs["tuning_type"] = py_config["bridge_tuning"] if tuning else None
        kwargs["bridge_name"] = interface_name
        kwargs["mtu"] = mtu

    if nad_type == SRIOV:
        kwargs["network_namespace"] = sriov_network_namespace
        kwargs["resource_name"] = sriov_resource_name
        kwargs["ipam"] = ipam

    if nad_type == OVS:
        kwargs["bridge_name"] = interface_name

    with NAD_TYPE[nad_type](**kwargs) as nad:
        yield nad


class EthernetNetworkConfigurationPolicy(NodeNetworkConfigurationPolicy):
    def __init__(
        self,
        name,
        interfaces_name=None,
        worker_pods=None,
        iface_state=NodeNetworkConfigurationPolicy.Interface.State.UP,
        node_selector=None,
        teardown=True,
        ipv4_enable=False,
        ipv4_dhcp=False,
        node_active_nics=None,
        ipv4_addresses=None,
        dns_resolver=None,
        routes=None,
    ):
        super().__init__(
            name=name,
            worker_pods=worker_pods,
            node_selector=node_selector,
            ipv4_enable=ipv4_enable,
            ipv4_dhcp=ipv4_dhcp,
            teardown=teardown,
            node_active_nics=node_active_nics,
            ipv4_addresses=ipv4_addresses,
            dns_resolver=dns_resolver,
            routes=routes,
        )
        self.interfaces_name = interfaces_name
        self.iface_state = iface_state

    def to_dict(self):
        res = super().to_dict()
        if self.interfaces_name:
            for nic in self.interfaces_name:
                self.iface = {
                    "name": nic,
                    "type": "ethernet",
                    "state": self.iface_state,
                }
                self.set_interface(interface=self.iface)
                res = super().to_dict()
        return res


def sriov_network_dict(namespace, network):
    """
    This function returns sriov network dictionary passed as an argument during vm creation
    """
    return {network.name: f"{namespace.name}/{network.name}"}


class MacPool:
    """
    Class to manage the mac addresses pool.
    to get this class, use mac_pool fixture.
    whenever you create a VM, before yield, call: mac_pool.append_macs(vm)
    and after yield, call: mac_pool.remove_macs(vm).
    """

    def __init__(self, kmp_range):
        self.range_start = self.mac_to_int(mac=kmp_range["RANGE_START"])
        self.range_end = self.mac_to_int(mac=kmp_range["RANGE_END"])
        self.pool = range(self.range_start, self.range_end + 1)
        self.used_macs = []

    def get_mac_from_pool(self):
        return self.mac_sampler(func=random.choice, seq=self.pool)

    def mac_sampler(self, func, *args, **kwargs):
        sampler = TimeoutSampler(wait_timeout=20, sleep=1, func=func, *args, **kwargs)
        for sample in sampler:
            mac = self.int_to_mac(num=sample)
            if mac not in self.used_macs:
                return mac

    @staticmethod
    def mac_to_int(mac):
        return int(netaddr.EUI(mac))

    @staticmethod
    def int_to_mac(num):
        mac = netaddr.EUI(num)
        mac.dialect = netaddr.mac_unix_expanded
        return str(mac)

    def append_macs(self, vm):
        for iface in vm.get_interfaces():
            self.used_macs.append(iface["macAddress"])

    def remove_macs(self, vm):
        for iface in vm.get_interfaces():
            self.used_macs.remove(iface["macAddress"])

    def mac_is_within_range(self, mac):
        return self.mac_to_int(mac) in self.pool


class IfaceNotFound(Exception):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"Interface not found for NAD {self.name}"


def get_vmi_mac_address_by_iface_name(vmi, iface_name):
    for iface in vmi.interfaces:
        if iface.name == iface_name:
            return iface.mac
    raise IfaceNotFound(name=iface_name)


def cloud_init_network_data(data):
    """
    Generate cloud init network data.
    https://cloudinit.readthedocs.io/en/latest/topics/network-config-format-v2.html

    data (dict): Dict of interface name and ip addresses.

    Examples:
        data = {
            "ethernets": {
                "eth1": {"addresses": ["192.168.10.1/24"]},
                "vlans": {
                    "eth1.10": {"addresses": ["192.168.10.3/24"], "id": 1000, "link": "eth1"}
                },
            }
        }
        cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
        network_data = cloud_init_network_data(data=data)
        cloud_init_data.update(network_data)
    """
    network_data = {"networkData": {"version": 2}}
    network_data["networkData"].update(data)

    return network_data


def ping(src_vm, dst_ip, packetsize=None, count=None):
    ping_ipv6 = "-6 " if get_ipv6_ip_str(dst_ip=dst_ip) else ""

    ping_cmd = f"ping {ping_ipv6}-w {count if count else '3'} {dst_ip}"
    if packetsize:
        ping_cmd += f" -s {packetsize} -M do"

    out = run_ssh_commands(host=src_vm.ssh_exec, commands=[shlex.split(ping_cmd)])[0]
    for line in out.splitlines():
        match = re.search("([0-9]+)% packet loss, ", line)
        if match:
            LOGGER.info(f"ping returned {match.string.strip()}")
            return match.groups()


def assert_ping_successful(src_vm, dst_ip, packetsize=None, count=None):
    if packetsize and packetsize > 1500:
        icmp_header = 8
        ip_header = 20
        packetsize = packetsize - ip_header - icmp_header

    assert (
        ping(src_vm=src_vm, dst_ip=dst_ip, packetsize=packetsize, count=count)[0] == "0"
    )


def get_ipv6_address(cnv_resource):
    """
    Attempt to find an IPv6 address in one of 2 possible resources - VirtualMachineInstance or Pod.

    Args:
        cnv_resource (Resource): VirtualMachineInstance or Pod

    Returns:
        str: First found IPv6 address, or None.
    """
    try:
        # Assume the resource type is VMI.
        addr_list = cnv_resource.interfaces[0]["ipAddresses"]
    except AttributeError:
        # Base assumption failed - so now assume the resource type is Pod.
        addr_list = [ip_addr["ip"] for ip_addr in cnv_resource.instance.status.podIPs]

    ipv6_list = [ip for ip in addr_list if get_ipv6_ip_str(dst_ip=ip)]
    return ipv6_list[0] if ipv6_list else None


def get_ipv6_ip_str(dst_ip):
    """
    Return the IPv6 address string if the input address is an IPv6 address, else None.
    """
    try:
        return ipaddress.IPv6Address(address=dst_ip)
    except ipaddress.AddressValueError:
        return


def ip_version_data_from_matrix(request):
    """
    Check if fixture ip_stack_version_matrix__<scope>__ is used in the flow, to indicate whether
    it's a dual-stack test or not.

    Args:
        request (fixtures.SubRequest): Test's parameterized request.

    Returns:
        str: The IP family (IPv4 or IPv6) is the matrix fixture is used, else None.
    """
    ip_stack_matrix_fixture = [
        fix_name
        for fix_name in request.fixturenames
        if "ip_stack_version_matrix__" in fix_name
    ]
    if not ip_stack_matrix_fixture:
        return
    return request.getfixturevalue(ip_stack_matrix_fixture[0])


def compose_cloud_init_data_dict(network_data=None, ipv6_network_data=None):
    init_data = FEDORA_CLOUD_INIT_PASSWORD
    interfaces_data = {"ethernets": {}}
    for data_input in [network_data, ipv6_network_data]:
        if data_input:
            interfaces_data["ethernets"].update(data_input["ethernets"])

    if interfaces_data["ethernets"]:
        init_data.update(cloud_init_network_data(data=interfaces_data))
    return init_data


def ovs_pods(admin_client, hco_namespace):
    pods = get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix=OVS_DS_NAME,
        namespace=hco_namespace,
        get_all=True,
    )
    return [
        pod for pod in pods or [] if pod.instance.status.phase == Pod.Status.RUNNING
    ]


def wait_for_ovs_pods(admin_client, hco_namespace, count=0):
    LOGGER.info(f"Wait for number of OVS pods to be: {count}")
    samples = TimeoutSampler(
        wait_timeout=150,
        sleep=1,
        func=ovs_pods,
        admin_client=admin_client,
        hco_namespace=hco_namespace,
    )
    num_of_pods = None
    try:
        for sample in samples:
            num_of_pods = len(sample)
            if num_of_pods == count:
                return True

    except TimeoutExpiredError:
        LOGGER.error(f"Found {num_of_pods} OVS PODs, expected: {count}")
        raise


def wait_for_ovs_status(network_addons_config, status=True):
    opt_log = "opt-in" if status else "opt-out"
    resource_log = f"{network_addons_config.kind} {network_addons_config.name}"
    LOGGER.info(f"Wait for {resource_log} OVS to be {opt_log}")
    samples = TimeoutSampler(
        wait_timeout=60,
        sleep=1,
        func=lambda: network_addons_config.instance.to_dict()["spec"].get("ovs"),
    )

    try:
        for sample in samples:
            if bool(sample is not None) == status:
                return True

    except TimeoutExpiredError:
        LOGGER.error(f"{resource_log} OVS should be {opt_log}")
        raise


def verify_ovs_installed_with_annotations(
    admin_client,
    ovs_daemonset,
    hyperconverged_ovs_annotations_fetched,
    network_addons_config,
):
    # Verify OVS
    wait_for_ovs_status(network_addons_config=network_addons_config)
    assert ovs_daemonset.exists, f"{OVS_DS_NAME} not found."
    ovs_daemonset.wait_until_deployed()
    # Verify annotations
    assert hyperconverged_ovs_annotations_fetched, "No ovs annotations found."
    # Verify pods
    wait_for_ovs_pods(
        admin_client=admin_client,
        hco_namespace=ovs_daemonset.namespace,
        count=ovs_daemonset.instance.status.desiredNumberScheduled,
    )


def get_ovs_daemonset(admin_client, hco_namespace):
    ovs_ds = list(
        DaemonSet.get(
            dyn_client=admin_client,
            namespace=hco_namespace.name,
            field_selector=f"metadata.name=={OVS_DS_NAME}",
        )
    )
    return ovs_ds[0] if ovs_ds else None


def wait_for_ovs_daemonset_deleted(ovs_daemonset):
    samples = TimeoutSampler(
        wait_timeout=90, sleep=1, func=lambda: ovs_daemonset.exists
    )
    try:
        for sample in samples:
            if not sample:
                return True

    except TimeoutExpiredError:
        LOGGER.error("OVS daemonset exists after opt-out")
        raise


def wait_for_ovs_daemonset_resource(admin_client, hco_namespace):
    samples = TimeoutSampler(
        wait_timeout=30,
        sleep=1,
        func=get_ovs_daemonset,
        admin_client=admin_client,
        hco_namespace=hco_namespace,
    )
    try:
        for sample in samples:
            if sample:
                return sample

    except TimeoutExpiredError:
        LOGGER.error("OVS daemonset doesn't exists after opt-in")
        raise


@contextlib.contextmanager
def network_device(
    interface_type,
    nncp_name,
    network_utility_pods=None,
    nodes=None,
    interface_name=None,
    ports=None,
    mtu=None,
    node_selector=None,
    ipv4_enable=False,
    ipv4_dhcp=False,
    priority=None,
    namespace=None,
    sriov_iface=None,
    sriov_resource_name=None,
):
    worker_pods = None
    nodes_names = (
        [node_selector] if node_selector else [node.name for node in nodes or []]
    )
    if network_utility_pods:
        worker_pods = [
            pod for pod in network_utility_pods if pod.node.name in nodes_names
        ]

    kwargs = {
        "name": nncp_name,
        "mtu": mtu,
    }
    if interface_type == SRIOV:
        kwargs["namespace"] = namespace
        kwargs["resource_name"] = sriov_resource_name
        kwargs["pf_names"] = sriov_iface.name
        kwargs["root_devices"] = sriov_iface.pciAddress
        # num_vfs is the pool of ifaces we want available in the sriov network
        # and should be no less than the number of multiple vm's we use in the tests
        # totalvfs is usually 64 or 128
        kwargs["num_vfs"] = min(sriov_iface.totalvfs, 10)
        kwargs["priority"] = priority or 99

    else:
        kwargs["bridge_name"] = interface_name
        if worker_pods:
            kwargs["worker_pods"] = worker_pods

        kwargs["ports"] = ports
        kwargs["node_selector"] = node_selector
        kwargs["ipv4_enable"] = ipv4_enable
        kwargs["ipv4_dhcp"] = ipv4_dhcp

    with NETWORK_DEVICE_TYPE[interface_type](**kwargs) as iface:
        yield iface


def enable_hyperconverged_ovs_annotations(
    admin_client,
    hco_namespace,
    hyperconverged_resource,
    network_addons_config,
):
    with ResourceEditor(
        patches={
            hyperconverged_resource: {"metadata": {"annotations": {DEPLOY_OVS: "true"}}}
        }
    ):
        wait_for_ovs_status(network_addons_config=network_addons_config, status=True)
        ovs_daemonset = wait_for_ovs_daemonset_resource(
            admin_client=admin_client, hco_namespace=hco_namespace
        )
        ovs_daemonset.wait_until_deployed()
        yield ovs_daemonset
