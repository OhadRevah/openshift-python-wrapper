import logging
from collections import namedtuple
from ipaddress import ip_interface
from itertools import chain
from time import sleep, time

import pytest
from openshift.dynamic.exceptions import InternalServerError

from resources.configmap import ConfigMap
from resources.deployment import Deployment
from resources.namespace import Namespace
from resources.pod import Pod
from tests.network.utils import linux_bridge_nad, running_vmi, nmcli_add_con_cmds
from tests.utils import (
    FedoraVirtualMachine,
    wait_for_vm_interfaces,
    Bridge,
    VXLANTunnel,
)

LOGGER = logging.getLogger(__name__)
BRIDGE_BR1 = "br1test"
KUBEMACPOOL_CONFIG_MAP_NAME = "kubemacpool-mac-range-config"
IfaceTuple = namedtuple("iface_config", ["ip_address", "mac_address", "name"])
CREATE_VM_TIMEOUT = 50
KUBEMACPOOL_NAMESPACE = "kubemacpool-system"


def restart_kubemacpool(default_client):
    for pod in Pod.get(
        dyn_client=default_client, label_selector="control-plane=mac-controller-manager"
    ):
        pod.delete(wait=True)

    kubemac_pool_deployment = Deployment(
        name="kubemacpool-mac-controller-manager", namespace=KUBEMACPOOL_NAMESPACE
    )
    kubemac_pool_deployment.wait_until_avail_replicas()


def create_vm(name, namespace, iface_config):

    # Even if kubemacpool is in running state is not operational.
    # We need try: except block as workaround.
    # In case if error occurs because of kubemacpool pod is not operational it will retry
    # Link to bug https://github.com/K8sNetworkPlumbingWG/kubemacpool/issues/50
    end_time = time() + CREATE_VM_TIMEOUT
    while time() < end_time:
        try:
            with VirtualMachineWithMultipleAttachments(
                namespace=namespace.name, name=name, iface_config=iface_config
            ) as vm:
                yield vm
                return
        except InternalServerError:  # Suppress exception if kubemacpool pod is not ready
            sleep(2)
    LOGGER.error(msg="Cannot create VM. Check kubemacpool status.")


def update_kubemacpool_scope(api_client, namespace, scope):
    kubemacpool_config_map = ConfigMap(
        namespace=namespace.name, name=KUBEMACPOOL_CONFIG_MAP_NAME
    )
    kubemacpool_config_map.update(
        resource_dict={
            "data": {"RANGE_START": scope[0], "RANGE_END": scope[1]},
            "metadata": {"name": KUBEMACPOOL_CONFIG_MAP_NAME},
        }
    )
    restart_kubemacpool(default_client=api_client)
    return kubemacpool_config_map.instance


class VirtualMachineWithMultipleAttachments(FedoraVirtualMachine):
    def __init__(self, name, namespace, iface_config):
        self.iface_config = iface_config

        networks = {}
        for config in self.iface_config.values():
            networks[config.name] = config.name

        super().__init__(
            name=name,
            namespace=namespace,
            networks=networks,
            interfaces=networks.keys(),
        )

    def _cloud_init_user_data(self):
        data = super()._cloud_init_user_data()
        bootcmds = list(
            chain.from_iterable(
                nmcli_add_con_cmds(iface, self.iface_config[iface].ip_address)
                for iface in ("eth%d" % idx for idx in range(1, 5))
            )
        )
        data["bootcmd"] = bootcmds
        runcmd = [
            # 2 kernel flags are used to disable wrong arp behavior
            "sysctl -w net.ipv4.conf.all.arp_ignore=1",
            # Send arp reply only if ip belongs to the interface
            "sysctl -w net.ipv4.conf.all.arp_announce=2",
        ]
        data["runcmd"] = runcmd
        return data

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

    def _to_dict(self):
        res = super()._to_dict()
        for mac, iface in zip(
            self.iface_config.values(),
            res["spec"]["template"]["spec"]["domain"]["devices"]["interfaces"][1:],
        ):
            if mac.mac_address != "auto":
                iface["macAddress"] = mac.mac_address
        return res


@pytest.fixture(scope="module", autouse=True)
def kubemacpool_namespace():
    return Namespace(name=KUBEMACPOOL_NAMESPACE)


@pytest.fixture(scope="module", autouse=True)
def kubemacpool_first_scope(default_client, kubemacpool_namespace):
    default_pool = ConfigMap(
        namespace=kubemacpool_namespace.name, name=KUBEMACPOOL_CONFIG_MAP_NAME
    )
    original_range_start = default_pool.instance["data"]["RANGE_START"]
    original_range_end = default_pool.instance["data"]["RANGE_END"]
    try:
        yield update_kubemacpool_scope(  # Create test pool
            api_client=default_client,
            namespace=kubemacpool_namespace,
            scope=("02:aa:bc:00:00:00", "02:aa:bc:ff:ff:ff"),
        )
    finally:
        update_kubemacpool_scope(  # Restore original mac pool
            api_client=default_client,
            namespace=kubemacpool_namespace,
            scope=(original_range_start, original_range_end),
        )


@pytest.fixture(scope="class")
def kubemacpool_second_scope(default_client, kubemacpool_namespace):
    # This fixture can update an existing MAC address range to the new one
    return update_kubemacpool_scope(
        api_client=default_client,
        namespace=kubemacpool_namespace,
        scope=("02:ff:fb:00:00:00", "02:ff:fb:ff:ff:ff"),
    )


@pytest.fixture(scope="module")
def namespace():
    with Namespace(name="kubemacpool-ns") as ns:
        yield ns


@pytest.fixture(scope="module")
def manual_mac_nad(namespace):
    with linux_bridge_nad(
        namespace=namespace, name="manual-mac-nad", bridge=BRIDGE_BR1
    ) as manual_mac_nad:
        yield manual_mac_nad


@pytest.fixture(scope="module")
def automatic_mac_nad(namespace):
    with linux_bridge_nad(
        namespace=namespace, name="automatic-mac-nad", bridge=BRIDGE_BR1
    ) as automatic_mac_nad:
        yield automatic_mac_nad


@pytest.fixture(scope="module")
def manual_mac_out_of_pool_nad(namespace):
    with linux_bridge_nad(
        namespace=namespace, name="manual-out-pool-mac-nad", bridge=BRIDGE_BR1
    ) as manual_mac_out_pool_nad:
        yield manual_mac_out_pool_nad


@pytest.fixture(scope="module")
def automatic_mac_tuning_net_nad(namespace):
    with linux_bridge_nad(
        namespace=namespace,
        name="automatic-mac-tun-net-nad",
        bridge=BRIDGE_BR1,
        tuning=True,
    ) as automatic_mac_tuning_net_nad:
        yield automatic_mac_tuning_net_nad


@pytest.fixture(scope="module")
def bridge_device(network_utility_pods):
    with Bridge(name=BRIDGE_BR1, worker_pods=network_utility_pods) as dev:
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
def vxlan(network_utility_pods, bridge_device, multi_nics_nodes, nodes_active_nics):

    # There is no need to build vxlan tunnel on bare metal because
    # it has enough physical interfaces for direct connection
    if multi_nics_nodes:
        yield
    else:
        with VXLANTunnel(
            name="kubemactest",
            worker_pods=network_utility_pods,
            vxlan_id=100,
            master_bridge=bridge_device.name,
            nodes_nics=nodes_active_nics,
        ) as vxlan:
            yield vxlan


@pytest.fixture(scope="module")
def vm_a(namespace, all_nads, bridge_device, vxlan, kubemacpool_first_scope):
    requested_network_config = {
        "eth1": IfaceTuple(
            ip_address="192.168.1.1", mac_address="02:aa:bc:00:00:10", name=all_nads[0]
        ),
        "eth2": IfaceTuple(
            ip_address="192.168.2.1", mac_address="auto", name=all_nads[1]
        ),
        "eth3": IfaceTuple(
            ip_address="192.168.3.1", mac_address="02:a4:c5:97:f7:11", name=all_nads[2]
        ),
        "eth4": IfaceTuple(
            ip_address="192.168.4.1", mac_address="auto", name=all_nads[3]
        ),
    }
    yield from create_vm(
        name="vm-fedora-a", iface_config=requested_network_config, namespace=namespace
    )


@pytest.fixture(scope="module")
def vm_b(namespace, all_nads, bridge_device, vxlan, kubemacpool_first_scope):
    requested_network_config = {
        "eth1": IfaceTuple(
            ip_address="192.168.1.2", mac_address="02:aa:bc:00:00:20", name=all_nads[0]
        ),
        "eth2": IfaceTuple(
            ip_address="192.168.2.2", mac_address="auto", name=all_nads[1]
        ),
        "eth3": IfaceTuple(
            ip_address="192.168.3.2", mac_address="02:a4:c5:97:f7:22", name=all_nads[2]
        ),
        "eth4": IfaceTuple(
            ip_address="192.168.4.2", mac_address="auto", name=all_nads[3]
        ),
    }
    yield from create_vm(
        name="vm-fedora-b", iface_config=requested_network_config, namespace=namespace
    )


@pytest.fixture(scope="module")
def started_vmi_a(vm_a):
    return running_vmi(vm_a)


@pytest.fixture(scope="module")
def started_vmi_b(vm_b):
    return running_vmi(vm_b)


@pytest.fixture(scope="class")
def configured_vm_a(vm_a, started_vmi_a):
    assert wait_for_vm_interfaces(vmi=started_vmi_a)
    return vm_a


@pytest.fixture(scope="class")
def configured_vm_b(vm_b, started_vmi_b):
    assert wait_for_vm_interfaces(vmi=started_vmi_b)
    return vm_b


@pytest.fixture(scope="function")
def restarted_vmi_a(vm_a):
    vm_a.stop(wait=True)
    return running_vmi(vm_a)


@pytest.fixture(scope="function")
def restarted_vmi_b(vm_b):
    vm_b.stop(wait=True)
    return running_vmi(vm_b)


@pytest.fixture(scope="class")
def vm_c(namespace, vm_a, all_nads):
    vm_a.delete(wait=True)
    requested_network_config = {
        "eth1": IfaceTuple(
            ip_address="192.168.1.1", mac_address="auto", name=all_nads[0]
        ),
        "eth2": IfaceTuple(
            ip_address="192.168.2.1", mac_address="auto", name=all_nads[1]
        ),
        "eth3": IfaceTuple(
            ip_address="192.168.3.1", mac_address="auto", name=all_nads[2]
        ),
        "eth4": IfaceTuple(
            ip_address="192.168.4.1", mac_address="auto", name=all_nads[3]
        ),
    }
    yield from create_vm(
        name="vm-fedora-c", iface_config=requested_network_config, namespace=namespace
    )


@pytest.fixture(scope="class")
def vm_d(namespace, vm_b, all_nads):
    vm_b.delete(wait=True)
    requested_network_config = {
        "eth1": IfaceTuple(
            ip_address="192.168.1.2", mac_address="auto", name=all_nads[0]
        ),
        "eth2": IfaceTuple(
            ip_address="192.168.2.2", mac_address="auto", name=all_nads[1]
        ),
        "eth3": IfaceTuple(
            ip_address="192.168.3.2", mac_address="auto", name=all_nads[2]
        ),
        "eth4": IfaceTuple(
            ip_address="192.168.4.2", mac_address="auto", name=all_nads[3]
        ),
    }
    yield from create_vm(
        name="vm-fedora-d", iface_config=requested_network_config, namespace=namespace
    )


@pytest.fixture(scope="class")
def started_vmi_c(vm_c):
    return running_vmi(vm_c)


@pytest.fixture(scope="class")
def started_vmi_d(vm_d):
    return running_vmi(vm_d)


@pytest.fixture(scope="class")
def booted_vm_c(vm_c, started_vmi_c):
    assert wait_for_vm_interfaces(vmi=started_vmi_c)
    return vm_c


@pytest.fixture(scope="class")
def booted_vm_d(vm_d, started_vmi_d):
    assert wait_for_vm_interfaces(vmi=started_vmi_d)
    return vm_d
