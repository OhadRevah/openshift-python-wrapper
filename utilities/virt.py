import logging
import os
import subprocess

import pexpect
from autologs.autologs import generate_logs
from resources.template import Template
from resources.utils import TimeoutExpiredError, TimeoutSampler
from resources.virtual_machine import VirtualMachine
from utilities.infra import generate_yaml_from_template


LOGGER = logging.getLogger(__name__)


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
    LOGGER.info(f"Wait until guest agent is active on {vmi.name}")
    try:
        for sample in sampler:
            #  Check if guest agent is activate
            agent_status = [
                i
                for i in sample.get("status", {}).get("conditions", {})
                if i.get("type") == "AgentConnected" and i.get("status") == "True"
            ]
            if agent_status:
                LOGGER.info(f"Wait until {vmi.name} report network interfaces status")
                for sample in sampler:
                    #  Get MVI interfaces from guest agent
                    ifcs = sample.get("status", {}).get("interfaces", [])
                    active_ifcs = [
                        i for i in ifcs if i.get("ipAddress") and i.get("interfaceName")
                    ]
                    if len(active_ifcs) == len(ifcs):
                        return True
                LOGGER.error(
                    f"{vmi.name} did not report network interfaces status in given time"
                )

    except TimeoutExpiredError:
        LOGGER.error(f"Guest agent is not installed or not active on {vmi.name}")
        raise


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
        dv=None,
        cloud_init_data=None,
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
        self.dv = dv
        self.cloud_init_data = cloud_init_data

    def _cloud_init_user_data(self):
        return {"password": "fedora", "chpasswd": "{ expire: False }"}

    def _to_dict(self):
        res = super()._to_dict()
        if self.dv:
            self.body = res

        if not self.body:
            self.body = generate_yaml_from_template(
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
            cloud_init_volume = {}
            for vol in spec["volumes"]:
                if vol["name"] == "cloudinitdisk":
                    cloud_init_volume = vol
                    break

            if not cloud_init_volume:
                spec["volumes"].append(
                    {"name": "cloudinitdisk", "cloudInitNoCloud": {"userData": None}}
                )
                cloud_init_volume = spec["volumes"][-1]

            cloud_init_volume["cloudInitNoCloud"][
                "userData"
            ] = _generate_cloud_init_user_data(
                self.cloud_init_data or self._cloud_init_user_data()
            )

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

        # Create rng device so the vm will able to use /dev/rnd without
        # waiting for entropy collecting.
        res["spec"]["template"]["spec"]["domain"]["devices"].setdefault("rng", {})

        if self.dv:
            spec["domain"]["devices"]["disks"].append(
                {"disk": {"bus": "virtio"}, "name": "dv-disk"}
            )
            spec["volumes"].append({"name": "dv-disk", "dataVolume": {"name": self.dv}})
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


class CommandExecFailed(Exception):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"Command: {self.name} - exec failed."


@generate_logs()
def _run_command(command):
    """
    Run command locally.

    Args:
        command (list): Command to run.

    Returns:
        tuple: True, out if command succeeded, False, err otherwise.
    """
    p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate()
    if err:
        LOGGER.error("Failed to run {cmd}. error: {err}".format(cmd=command, err=err))
        return False, err

    if p.returncode != 0:
        LOGGER.error(
            "Failed to run {cmd}. rc: {rc}".format(cmd=command, rc=p.returncode)
        )
        return False, out.decode("utf-8")

    return True, out.decode("utf-8")


def run_virtctl_command(command, namespace=None):
    """
    Run virtctl command

    Args:
        command (list): Command to run
        namespace (str): Namespace to send to virtctl command

    Returns:
        tuple: True, out if command succeeded, False, err otherwise.
    """
    virtctl_cmd = ["virtctl"]
    kubeconfig = os.getenv("KUBECONFIG")
    if namespace:
        virtctl_cmd = virtctl_cmd + ["-n", namespace]

    if kubeconfig:
        virtctl_cmd = virtctl_cmd + ["--kubeconfig", kubeconfig]

    virtctl_cmd = virtctl_cmd + command
    return _run_command(command=virtctl_cmd)
