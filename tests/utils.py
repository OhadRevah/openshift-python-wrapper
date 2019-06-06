import logging
import urllib.error
import urllib.request
import ssl

from autologs.autologs import generate_logs
from pytest_testconfig import config as py_config

from resources.virtual_machine import VirtualMachine
from utilities import utils

LOGGER = logging.getLogger(__name__)


@generate_logs()
def wait_for_vm_interfaces(vmi, timeout=600):
    """
    Wait until guest agent report VMI network interfaces.

    Args:
        vmi (VirtualMachineInstance): VMI object.
        timeout (int): Maximum time to wait for interfaces status

    Returns:
        bool: True if agent report VMI interfaces.

    Raises:
        TimeoutExpiredError: After timeout reached.
    """
    sampler = utils.TimeoutSampler(timeout=timeout, sleep=1, func=lambda: vmi.instance)
    LOGGER.info("Wait until guest agent is active")
    try:
        for sample in sampler:
            #  Check if guest agent is activate
            agent_status = [
                i
                for i in sample.get("status", {}).get("conditions", {})
                if i.get("type") == "AgentConnected" and i.get("status") == "True"
            ]
            if agent_status:
                LOGGER.info("Wait until VMI report network interfaces status")
                for sample in sampler:
                    #  Get MVI interfaces from guest agent
                    ifcs = sample.get("status", {}).get("interfaces", [])
                    active_ifcs = [
                        i for i in ifcs if i.get("ipAddress") and i.get("interfaceName")
                    ]
                    if len(active_ifcs) == len(ifcs):
                        return True
                LOGGER.error(
                    "VMI did not report network interfaces status in given time"
                )

    except utils.TimeoutExpiredError:
        LOGGER.error("Guest agent is not installed or not active")
        raise


def get_images_http_server():
    """
    Fetch http_server url from config and return if available.
    """
    region = py_config["region"]
    server = py_config[region]["http_server"]
    try:
        assert urllib.request.urlopen(server).getcode() == 200
    except urllib.error.URLError:
        LOGGER.error("URL Error when testing connectivity to HTTP server")
        raise

    return server


def _generate_cloud_init_user_data(user_data):
    data = "#cloud-config\n"
    for k, v in user_data.items():
        if isinstance(v, list):
            list_len = len(v) - 1
            data += f"{k}:\n    "
            for i, item in enumerate(v):
                data += f"- {item}\n{'' if i == list_len else '    '}"
        else:
            data += f"{k}: {v}\n"

    return data


def get_images_https_server():
    """
    Fetch https_server url from config and return if available.
    """
    region = py_config["region"]
    server = py_config[region]["https_server"]

    myssl = ssl.create_default_context()
    myssl.check_hostname = False
    myssl.verify_mode = ssl.CERT_NONE
    try:
        assert urllib.request.urlopen(server, context=myssl).getcode() == 200
    except urllib.error.URLError:
        LOGGER.error("URL Error when testing connectivity to HTTPS server")
        raise
    return server


class FedoraVirtualMachine(VirtualMachine):
    def __init__(
        self,
        name,
        namespace,
        eviction=None,
        client=None,
        interfaces=None,
        networks=None,
        node_selector=None,
        cpu_flags=None,
        **vm_attr,
    ):
        super().__init__(name=name, namespace=namespace, client=client)
        self.interfaces = interfaces or []
        self.networks = networks or {}
        self.node_selector = node_selector
        self.eviction = eviction
        self.vm_attrs = vm_attr
        self.vm_attrs_to_use = self.vm_attrs or {
            "label": "fedora-vm",
            "cpu_cores": 1,
            "memory": "1024Mi",
        }
        self.cpu_flags = cpu_flags

    def _cloud_init_user_data(self):
        return {"password": "fedora", "chpasswd": "{ expire: False }"}

    def _to_dict(self):
        res = super()._to_dict()
        json_out = utils.generate_yaml_from_template(
            file_="tests/manifests/vm-fedora.yaml",
            name=self.name,
            **self.vm_attrs_to_use,
        )

        res["metadata"] = json_out["metadata"]
        res["spec"] = json_out["spec"]

        for iface_name in self.interfaces:
            res["spec"]["template"]["spec"]["domain"]["devices"]["interfaces"].append(
                {"name": iface_name, "bridge": {}}
            )

        for iface_name, network in self.networks.items():
            res["spec"]["template"]["spec"]["networks"].append(
                {"name": iface_name, "multus": {"networkName": network}}
            )

        for vol in res["spec"]["template"]["spec"]["volumes"]:
            if vol["name"] == "cloudinitdisk":
                vol["cloudInitNoCloud"]["userData"] = _generate_cloud_init_user_data(
                    self._cloud_init_user_data()
                )
                break

        if self.node_selector:
            res["spec"]["template"]["spec"]["nodeSelector"] = {
                "kubernetes.io/hostname": self.node_selector
            }

        if self.cpu_flags:
            res["spec"]["template"]["spec"]["domain"]["cpu"] = self.cpu_flags

        if self.eviction:
            res["spec"]["template"]["spec"]["evictionStrategy"] = "LiveMigrate"

        return res
