import logging
from collections import namedtuple
from ipaddress import ip_interface

from resources.pod import Pod
from resources.utils import TimeoutExpiredError, TimeoutSampler

from utilities.network import cloud_init_network_data, get_vmi_mac_address_by_iface_name
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
)


LOGGER = logging.getLogger(__name__)
KMP_PODS_LABEL = "control-plane=mac-controller-manager"
IfaceTuple = namedtuple("iface_config", ["ip_address", "mac_address", "name"])


def vm_network_config(mac_pool, all_nads, end_ip, mac_uid):
    """end_ip - int in range [1,254]"""
    """mac_uid - string in range ['0','f'] in hex"""
    return {
        "eth1": IfaceTuple(
            ip_address=f"10.200.1.{end_ip}",
            mac_address=mac_pool.get_mac_from_pool(),
            name=all_nads[0],
        ),
        "eth2": IfaceTuple(
            ip_address=f"10.200.2.{end_ip}", mac_address="auto", name=all_nads[1]
        ),
        "eth3": IfaceTuple(
            ip_address=f"10.200.3.{end_ip}",
            mac_address=f"02:0{mac_uid}:00:00:00:00",
            name=all_nads[2],
        ),
        "eth4": IfaceTuple(
            ip_address=f"10.200.4.{end_ip}", mac_address="auto", name=all_nads[3]
        ),
    }


def get_pods(dyn_client, namespace, label=None):
    return list(
        Pod.get(
            dyn_client=dyn_client,
            namespace=namespace.name,
            label_selector=label,
        )
    )


def wait_for_kmp_pods_creation(dyn_client, namespace, replicas):
    samples = TimeoutSampler(
        timeout=120,
        sleep=1,
        func=get_pods,
        dyn_client=dyn_client,
        namespace=namespace,
        label=KMP_PODS_LABEL,
    )
    for sample in samples:
        if len(sample) == replicas:
            return


def wait_for_pods_deletion(pods):
    for pod in pods:
        pod.wait_deleted()


def wait_for_kmp_pods_to_be_in_crashloop(dyn_client, namespace):
    for pod in get_pods(
        dyn_client=dyn_client, namespace=namespace, label=KMP_PODS_LABEL
    ):
        LOGGER.info(
            f"Wait for {pod.name} container status to be {Pod.Status.CRASH_LOOPBACK_OFF}"
        )
        pod_states = TimeoutSampler(
            timeout=30,
            sleep=1,
            func=lambda: pod.instance.status.containerStatuses[0].state,
        )
        try:
            for pod_state in pod_states:
                if pod_state.waiting:
                    if pod_state.waiting.reason == Pod.Status.CRASH_LOOPBACK_OFF:
                        break
        except TimeoutExpiredError:
            LOGGER.error(
                f"{pod.name} container did not get status {Pod.Status.CRASH_LOOPBACK_OFF}"
            )
            raise


def create_vm(name, namespace, iface_config, client, mac_pool):
    network_data_data = {}
    _data = {
        iface: {"addresses": [f"{iface_config[iface].ip_address}/24"]}
        for iface in ("eth%d" % idx for idx in range(1, 5))
    }
    network_data_data["ethernets"] = _data
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data.update(cloud_init_network_data(data=network_data_data))

    runcmd = [
        # 2 kernel flags are used to disable wrong arp behavior
        "sysctl -w net.ipv4.conf.all.arp_ignore=1",
        # Send arp reply only if ip belongs to the interface
        "sysctl -w net.ipv4.conf.all.arp_announce=2",
    ]
    cloud_init_data["userData"]["runcmd"] = runcmd

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
            ip_address=ip_interface(pod_iface_config["ipAddress"]).ip,
            mac_address="auto",
            name=pod_iface_config["name"],
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


def assert_macs_preseved(vm):
    for iface in vm.get_interfaces():
        assert iface.macAddress == get_vmi_mac_address_by_iface_name(
            vmi=vm.vmi, iface_name=iface.name
        )


def assert_manual_mac_configured(vm, iface_config):
    assert iface_config.mac_address == get_vmi_mac_address_by_iface_name(
        vmi=vm.vmi, iface_name=iface_config.name
    )