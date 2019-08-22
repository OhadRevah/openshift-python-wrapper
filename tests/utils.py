import contextlib
import logging
import socket
import ssl
import urllib.error
import urllib.request

import pexpect
from autologs.autologs import generate_logs
from pytest_testconfig import config as py_config
from resources.datavolume import ImportFromHttpDataVolume
from resources.namespace import Namespace
from resources.node_network_configuration_policy import NodeNetworkConfigurationPolicy
from resources.node_network_state import NodeNetworkState
from resources.project import Project, ProjectRequest
from resources.template import Template
from resources.utils import TimeoutExpiredError, TimeoutSampler
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
        LOGGER.info(f"Testing connectivity to {server} HTTP server")
        assert urllib.request.urlopen(server, timeout=60).getcode() == 200
    except (urllib.error.URLError, socket.timeout) as e:
        LOGGER.error(
            f"URL Error when testing connectivity to {server} HTTP server.\nError: {e}"
        )
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


class VirtualMachineForTests(VirtualMachine):
    def __init__(
        self,
        name,
        namespace,
        body=None,
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
        set_cloud_init=True,
    ):
        super().__init__(name=name, namespace=namespace, client=client)
        self.body = body
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
        self.set_cloud_init = set_cloud_init

    def _cloud_init_user_data(self):
        return {"password": "fedora", "chpasswd": "{ expire: False }"}

    def _to_dict(self):
        res = super()._to_dict()
        if not self.body:
            self.body = utils.generate_yaml_from_template(
                file_="tests/manifests/vm-fedora.yaml", name=self.name
            )

        res["metadata"] = self.body["metadata"]
        res["spec"] = self.body["spec"]

        spec = res["spec"]["template"]["spec"]
        for iface_name in self.interfaces:
            spec["domain"]["devices"]["interfaces"].append(
                {"name": iface_name, "bridge": {}}
            )

        for iface_name, network in self.networks.items():
            spec["networks"].append(
                {"name": iface_name, "multus": {"networkName": network}}
            )

        if self.set_cloud_init:
            for vol in spec["volumes"]:
                if vol["name"] == "cloudinitdisk":
                    vol["cloudInitNoCloud"][
                        "userData"
                    ] = _generate_cloud_init_user_data(self._cloud_init_user_data())
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


def get_template_by_labels(client, labels):
    labels = [f"{label}=true" for label in labels]
    template = Template.get(
        dyn_client=client,
        singular_name=Template.singular_name,
        namespace="openshift",
        label_selector=",".join(labels),
    )
    return list(template)[0]


class DataVolumeTestResource(ImportFromHttpDataVolume):
    def __init__(
        self,
        name,
        namespace,
        url,
        os_release,
        template_labels,
        size="25Gi",
        storage_class=None,
        content_type=ImportFromHttpDataVolume.ContentType.KUBEVIRT,
        access_modes=ImportFromHttpDataVolume.AccessMode.RWO,
    ):
        storage_class = storage_class or py_config["storage_defaults"]["storage_class"]
        super().__init__(
            name=name,
            namespace=namespace,
            size=size,
            storage_class=storage_class,
            url=url,
            content_type=content_type,
            access_modes=access_modes,
        )
        self.os_release = os_release
        self.template_labels = template_labels


class CommandExecFailed(Exception):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"Command: {self.name} - exec failed."


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


def vm_console_run_commands(console_impl, vm, commands, timeout=60):
    """
    Run a list of commands inside VM and check all commands return 0.
    If return code other than 0 then it will break execution and raise exception.

    Args:
        console_impl (Console): Console implementation (RHEL, Fedora, etc)
        vm (obj): VirtualMachine
        commands (list): List of commands
        timeout (int): Time to wait for the command output
    """
    with console_impl(vm=vm) as vmc:
        for command in commands:
            LOGGER.info(f"Execute {command} on {vm.name}")
            vmc.sendline(command)
            vmc.sendline(
                "echo rc==$?=="
            )  # This construction rc==$?== is unique. Return code validation
            try:
                vmc.expect("rc==0==", timeout=timeout)  # Expected return code is 0
            except pexpect.exceptions.TIMEOUT:
                raise CommandExecFailed(command)


def create_ns(client, name):
    if not client:
        with Namespace(name=name) as ns:
            ns.wait_for_status(Namespace.Status.ACTIVE, timeout=120)
            yield ns
    else:
        with ProjectRequest(name=name, client=client):
            project = Project(name=name, client=client)
            project.wait_for_status(Project.Status.ACTIVE, timeout=120)
            yield project


def _disable_vlan_filtering(pod, bridge_name):
    # This is a temporal measure there are some tests where we need
    # trunk but that will be fixed at future versions of CNI linux-bridge [1]
    # [1] https://jira.coreos.com/browse/CNV-1804
    # [2] https://jira.coreos.com/browse/CNV-2455
    pod.execute(
        [
            "ip",
            "link",
            "set",
            "dev",
            bridge_name,
            "type",
            "bridge",
            "vlan_filtering",
            "0",
        ]
    )


def _set_iface_mtu(pod, port, mtu):
    pod.execute(command=["ip", "link", "set", port, "mtu", mtu])


class LinuxBridgeNodeNetworkConfigurationPolicy(NodeNetworkConfigurationPolicy):
    def __init__(
        self,
        name,
        worker_pods,
        bridge_name,
        ports=None,
        mtu=None,
        vlan_filtering=True,
        node_selector=None,
    ):
        """
        Create bridge on nodes (according node_selector, all if no selector presents)

        Args:
            name (str): Policy name.
            worker_pods (list): List of Pods instances.
            bridge_name (str): Bridge name.
            ports (list): The bridge's slave port(s).
            mtu (int): MTU size
            vlan_filtering: determines if vlan_filtering configured at node bridges
        """
        super().__init__(name=name)
        self._worker_pods = worker_pods
        self.bridge_name = bridge_name
        self.ports = ports or []
        self.mtu = mtu
        self.vlan_filtering = vlan_filtering
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
                if not self.vlan_filtering:
                    _disable_vlan_filtering(pod, self.bridge_name)
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
