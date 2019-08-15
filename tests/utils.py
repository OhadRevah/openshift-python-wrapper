import logging
import ssl
import urllib.error
import urllib.request

from autologs.autologs import generate_logs
from pytest_testconfig import config as py_config

from resources.utils import TimeoutSampler, TimeoutExpiredError
from resources.virtual_machine import VirtualMachine
from utilities import utils

LOGGER = logging.getLogger(__name__)


@generate_logs()
def wait_for_vm_interfaces(vmi, timeout=720):
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
    sampler = TimeoutSampler(timeout=timeout, sleep=1, func=lambda: vmi.instance)
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

    except TimeoutExpiredError:
        LOGGER.error("Guest agent is not installed or not active")
        raise


def get_images_external_http_server():
    """
    Fetch http_server url from config and return if available.
    """
    server = py_config[py_config["region"]]["http_server"]
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
        service_accounts=None,
        cpu_flags=None,
        cpu_limits=None,
        cpu_requests=None,
        cpu_sockets=None,
        cpu_cores=None,
        cpu_threads=None,
        memory=None,
        label=None,
    ):
        super().__init__(name=name, namespace=namespace, client=client)
        self.interfaces = interfaces or []
        self.service_accounts = service_accounts or []
        self.networks = networks or {}
        self.node_selector = node_selector
        self.eviction = eviction
        self.cpu_flags = cpu_flags
        self.cpu_limits = cpu_limits
        self.cpu_requests = cpu_requests
        self.cpu_sockets = cpu_sockets
        self.cpu_cores = cpu_cores
        self.cpu_threads = cpu_threads
        self.memory = memory
        self.label = label

    def _cloud_init_user_data(self):
        return {"password": "fedora", "chpasswd": "{ expire: False }"}

    def _to_dict(self):
        res = super()._to_dict()
        json_out = utils.generate_yaml_from_template(
            file_="tests/manifests/vm-fedora.yaml", name=self.name
        )

        res["metadata"] = json_out["metadata"]
        res["spec"] = json_out["spec"]

        spec = res["spec"]["template"]["spec"]
        for iface_name in self.interfaces:
            spec["domain"]["devices"]["interfaces"].append(
                {"name": iface_name, "bridge": {}}
            )

        for iface_name, network in self.networks.items():
            spec["networks"].append(
                {"name": iface_name, "multus": {"networkName": network}}
            )

        for vol in spec["volumes"]:
            if vol["name"] == "cloudinitdisk":
                vol["cloudInitNoCloud"]["userData"] = _generate_cloud_init_user_data(
                    self._cloud_init_user_data()
                )
                break

        for sa in self.service_accounts:
            spec["domain"]["devices"]["disks"].append({"disk": {}, "name": sa})
            spec["volumes"].append(
                {"name": sa, "serviceAccount": {"serviceAccountName": sa}}
            )

        if self.node_selector:
            spec["nodeSelector"] = {"kubernetes.io/hostname": self.node_selector}

        if self.eviction:
            spec["evictionStrategy"] = "LiveMigrate"

        # cpu settings
        if self.cpu_flags:
            spec["domain"]["cpu"] = self.cpu_flags

        if self.cpu_limits:
            spec["domain"]["resources"].setdefault("limits", {})
            spec["domain"]["resources"]["limits"].update({"cpu": self.cpu_limits})

        if self.cpu_requests:
            spec["domain"]["resources"].setdefault("requests", {})
            spec["domain"]["resources"]["requests"].update({"cpu": self.cpu_requests})

        if self.cpu_cores:
            spec["domain"]["cpu"]["cores"] = self.cpu_cores

        if self.cpu_threads:
            spec["domain"]["cpu"]["threads"] = self.cpu_threads

        if self.cpu_sockets:
            spec["domain"]["cpu"]["sockets"] = self.cpu_sockets

        if self.memory:
            spec["domain"]["resources"]["requests"]["memory"] = self.memory

        if self.label:
            res["spec"]["template"]["metadata"]["labels"]["kubevirt.io/vm"] = self.label

        return res
