import logging
import random
from collections import namedtuple
from ipaddress import ip_interface
from itertools import chain

import netaddr
import pytest
import tests.network.utils as network_utils
import utilities.network
from resources.configmap import ConfigMap
from resources.utils import TimeoutSampler
from tests.network.utils import nmcli_add_con_cmds, running_vmi
from utilities.infra import create_ns
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


LOGGER = logging.getLogger(__name__)
BRIDGE_BR1 = "br1test"
KUBEMACPOOL_CONFIG_MAP_NAME = "kubemacpool-mac-range-config"
IfaceTuple = namedtuple("iface_config", ["ip_address", "mac_address", "name"])
CREATE_VM_TIMEOUT = 50


def create_vm(name, namespace, iface_config, client, mac_pool):
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    bootcmds = list(
        chain.from_iterable(
            nmcli_add_con_cmds(iface=iface, ip=iface_config[iface].ip_address)
            for iface in ("eth%d" % idx for idx in range(1, 5))
        )
    )
    cloud_init_data["bootcmd"] = bootcmds
    runcmd = [
        # 2 kernel flags are used to disable wrong arp behavior
        "sysctl -w net.ipv4.conf.all.arp_ignore=1",
        # Send arp reply only if ip belongs to the interface
        "sysctl -w net.ipv4.conf.all.arp_announce=2",
    ]
    cloud_init_data["runcmd"] = runcmd

    with VirtualMachineWithMultipleAttachments(
        namespace=namespace.name,
        name=name,
        iface_config=iface_config,
        client=client,
        cloud_init_data=cloud_init_data,
    ) as vm:
        mac_pool.append_macs(vm=vm)
        yield vm
        mac_pool.remove_macs(vm=vm)


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
        sampler = TimeoutSampler(timeout=20, sleep=1, func=func, *args, **kwargs)
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


class VirtualMachineWithMultipleAttachments(VirtualMachineForTests):
    def __init__(
        self, name, namespace, iface_config, client=None, cloud_init_data=None
    ):
        self.iface_config = iface_config

        networks = {}
        for config in self.iface_config.values():
            networks[config.name] = config.name

        super().__init__(
            name=name,
            namespace=namespace,
            networks=networks,
            interfaces=networks.keys(),
            client=client,
            cloud_init_data=cloud_init_data,
        )

    @property
    def default_masquerade_iface_config(self):
        pod_iface_config = self.vmi.instance["status"]["interfaces"][0]
        return IfaceTuple(
            ip_interface(pod_iface_config["ipAddress"]).ip,
            "auto",
            pod_iface_config["name"],
        )

    @property
    def manual_mac_iface_config(self):
        return self.iface_config["eth1"]

    @property
    def auto_mac_iface_config(self):
        return self.iface_config["eth2"]

    @property
    def manual_mac_out_pool_iface_config(self):  # Manually assigned mac out of pool
        return self.iface_config["eth3"]

    @property
    def auto_mac_tuning_iface_config(self):
        return self.iface_config["eth4"]

    def to_dict(self):
        self.body = fedora_vm_body(name=self.name)
        res = super().to_dict()
        for mac, iface in zip(
            self.iface_config.values(),
            res["spec"]["template"]["spec"]["domain"]["devices"]["interfaces"][1:],
        ):
            if mac.mac_address != "auto":
                iface["macAddress"] = mac.mac_address
        return res


@pytest.fixture(scope="module")
def manual_mac_nad(namespace):
    with utilities.network.bridge_nad(
        nad_type=utilities.network.LINUX_BRIDGE,
        nad_name="manual-mac-nad",
        bridge_name=BRIDGE_BR1,
        namespace=namespace,
    ) as manual_mac_nad:
        yield manual_mac_nad


@pytest.fixture(scope="module")
def automatic_mac_nad(namespace):
    with utilities.network.bridge_nad(
        nad_type=utilities.network.LINUX_BRIDGE,
        nad_name="automatic-mac-nad",
        bridge_name=BRIDGE_BR1,
        namespace=namespace,
    ) as automatic_mac_nad:
        yield automatic_mac_nad


@pytest.fixture(scope="module")
def manual_mac_out_of_pool_nad(namespace):
    with utilities.network.bridge_nad(
        nad_type=utilities.network.LINUX_BRIDGE,
        nad_name="manual-out-pool-mac-nad",
        bridge_name=BRIDGE_BR1,
        namespace=namespace,
        tuning=True,
    ) as manual_mac_out_pool_nad:
        yield manual_mac_out_pool_nad


@pytest.fixture(scope="module")
def automatic_mac_tuning_net_nad(namespace):
    with utilities.network.bridge_nad(
        nad_type=utilities.network.LINUX_BRIDGE,
        nad_name="automatic-mac-tun-net-nad",
        bridge_name=BRIDGE_BR1,
        namespace=namespace,
        tuning=True,
    ) as automatic_mac_tuning_net_nad:
        yield automatic_mac_tuning_net_nad


@pytest.fixture(scope="module")
def bridge_device(
    skip_if_no_multinic_nodes,
    nodes_active_nics,
    network_utility_pods,
    schedulable_nodes,
):
    with network_utils.bridge_device(
        bridge_type=utilities.network.LINUX_BRIDGE,
        nncp_name="kubemacpool",
        bridge_name=BRIDGE_BR1,
        network_utility_pods=network_utility_pods,
        nodes=schedulable_nodes,
        ports=[
            utilities.network.get_hosts_common_ports(
                nodes_active_nics=nodes_active_nics
            )[1]
        ],
    ) as dev:
        yield dev


@pytest.fixture(scope="module")
def all_nads(
    manual_mac_nad,
    automatic_mac_nad,
    manual_mac_out_of_pool_nad,
    automatic_mac_tuning_net_nad,
):
    return [
        manual_mac_nad.name,
        automatic_mac_nad.name,
        manual_mac_out_of_pool_nad.name,
        automatic_mac_tuning_net_nad.name,
    ]


@pytest.fixture(scope="module")
def kubemacpool_range(hco_namespace):
    default_pool = ConfigMap(
        namespace=hco_namespace.name, name=KUBEMACPOOL_CONFIG_MAP_NAME
    )
    return default_pool.instance["data"]


@pytest.fixture(scope="module")
def mac_pool(kubemacpool_range):
    return MacPool(kmp_range=kubemacpool_range)


@pytest.fixture(scope="class")
def vm_a(
    namespace, all_nads, bridge_device, mac_pool, unprivileged_client,
):
    requested_network_config = {
        "eth1": IfaceTuple(
            ip_address="10.200.1.1",
            mac_address=mac_pool.get_mac_from_pool(),
            name=all_nads[0],
        ),
        "eth2": IfaceTuple(
            ip_address="10.200.2.1", mac_address="auto", name=all_nads[1]
        ),
        "eth3": IfaceTuple(
            ip_address="10.200.3.1", mac_address="02:01:00:00:00:00", name=all_nads[2],
        ),
        "eth4": IfaceTuple(
            ip_address="10.200.4.1", mac_address="auto", name=all_nads[3]
        ),
    }
    yield from create_vm(
        name="vm-fedora-a",
        iface_config=requested_network_config,
        namespace=namespace,
        client=unprivileged_client,
        mac_pool=mac_pool,
    )


@pytest.fixture(scope="class")
def vm_b(
    namespace, all_nads, bridge_device, mac_pool, unprivileged_client,
):
    requested_network_config = {
        "eth1": IfaceTuple(
            ip_address="10.200.1.2",
            mac_address=mac_pool.get_mac_from_pool(),
            name=all_nads[0],
        ),
        "eth2": IfaceTuple(
            ip_address="10.200.2.2", mac_address="auto", name=all_nads[1]
        ),
        "eth3": IfaceTuple(
            ip_address="10.200.3.2", mac_address="02:02:00:00:00:00", name=all_nads[2],
        ),
        "eth4": IfaceTuple(
            ip_address="10.200.4.2", mac_address="auto", name=all_nads[3]
        ),
    }
    yield from create_vm(
        name="vm-fedora-b",
        iface_config=requested_network_config,
        namespace=namespace,
        client=unprivileged_client,
        mac_pool=mac_pool,
    )


@pytest.fixture(scope="class")
def started_vmi_a(vm_a):
    return running_vmi(vm=vm_a)


@pytest.fixture(scope="class")
def started_vmi_b(vm_b):
    return running_vmi(vm=vm_b)


@pytest.fixture(scope="class")
def running_vm_a(vm_a, started_vmi_a):
    wait_for_vm_interfaces(vmi=started_vmi_a)
    return vm_a


@pytest.fixture(scope="class")
def running_vm_b(vm_b, started_vmi_b):
    wait_for_vm_interfaces(vmi=started_vmi_b)
    return vm_b


@pytest.fixture(scope="function")
def restarted_vmi_a(vm_a):
    vm_a.stop(wait=True)
    return running_vmi(vm=vm_a)


@pytest.fixture(scope="function")
def restarted_vmi_b(vm_b):
    vm_b.stop(wait=True)
    return running_vmi(vm=vm_b)


@pytest.fixture(scope="class")
def opted_out_ns_vm(opted_out_ns, opted_out_ns_nad, mac_pool):
    networks = {opted_out_ns_nad.name: opted_out_ns_nad.name}
    name = f"{opted_out_ns.name}-vm"
    with VirtualMachineForTests(
        namespace=opted_out_ns.name,
        name=name,
        networks=networks,
        interfaces=networks.keys(),
        body=fedora_vm_body(name),
    ) as vm:
        mac_pool.append_macs(vm=vm)
        yield vm
        mac_pool.remove_macs(vm=vm)


@pytest.fixture(scope="class")
def wrong_label_ns_vm(wrong_label_ns, wrong_label_ns_nad, mac_pool):
    networks = {wrong_label_ns_nad.name: wrong_label_ns_nad.name}
    name = f"{wrong_label_ns.name}-vm"
    with VirtualMachineForTests(
        namespace=wrong_label_ns.name,
        name=name,
        networks=networks,
        interfaces=networks.keys(),
        body=fedora_vm_body(name),
    ) as vm:
        mac_pool.append_macs(vm=vm)
        yield vm
        mac_pool.remove_macs(vm=vm)


@pytest.fixture(scope="class")
def opted_out_ns_started_vmi(opted_out_ns_vm):
    return running_vmi(vm=opted_out_ns_vm)


@pytest.fixture(scope="class")
def wrong_label_ns_started_vmi(wrong_label_ns_vm):
    return running_vmi(vm=wrong_label_ns_vm)


@pytest.fixture(scope="class")
def opted_out_ns_running_vm(opted_out_ns_vm, opted_out_ns_started_vmi):
    wait_for_vm_interfaces(vmi=opted_out_ns_started_vmi)
    return opted_out_ns_vm


@pytest.fixture(scope="class")
def wrong_label_ns_running_vm(wrong_label_ns_vm, wrong_label_ns_started_vmi):
    wait_for_vm_interfaces(vmi=wrong_label_ns_started_vmi)
    return wrong_label_ns_vm


@pytest.fixture(scope="class")
def opted_out_ns_nad(opted_out_ns, bridge_device):
    with utilities.network.bridge_nad(
        nad_type=bridge_device.bridge_type,
        nad_name=f"{opted_out_ns.name}-nad",
        bridge_name=bridge_device.bridge_name,
        namespace=opted_out_ns,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def wrong_label_ns_nad(wrong_label_ns, bridge_device):
    with utilities.network.bridge_nad(
        nad_type=bridge_device.bridge_type,
        nad_name=f"{wrong_label_ns.name}-nad",
        bridge_name=bridge_device.bridge_name,
        namespace=wrong_label_ns,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def opted_out_ns():
    yield from create_ns(name="kmp-opted-out")


@pytest.fixture(scope="class")
def wrong_label_ns(kmp_vm_label):
    kmp_vm_label["mutatevirtualmachines.kubemacpool.io"] += "-wrong-label"
    yield from create_ns(name="kmp-wrong-label", kmp_vm_label=kmp_vm_label)
