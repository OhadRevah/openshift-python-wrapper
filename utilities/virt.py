import logging
import os
import subprocess

import pexpect
from autologs.autologs import generate_logs
from resources.service import Service
from resources.template import Template
from resources.utils import TimeoutExpiredError, TimeoutSampler
from resources.virtual_machine import VirtualMachine
from utilities.infra import generate_yaml_from_template


LOGGER = logging.getLogger(__name__)

K8S_TAINT = "node.kubernetes.io/unschedulable"
NO_SCHEDULE = "NoSchedule"
CIRROS_IMAGE = "kubevirt/cirros-container-disk-demo:latest"
FEDORA_CLOUD_INIT_PASSWORD = {"password": "fedora", "chpasswd": "{ expire: False }"}


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
        dv=None,
        cloud_init_data=None,
        machine_type=None,
        image=None,
        ssh=False,
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
        self.dv = dv
        self.cloud_init_data = cloud_init_data
        self.machine_type = machine_type
        self.image = image
        self.ssh = ssh
        self.ssh_service = None
        self.ssh_node_port = None

    def __enter__(self):
        super().__enter__()
        if self.ssh:
            self.ssh_enable()
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        super().__exit__(exception_type, exception_value, traceback)
        if self.ssh_service:
            self.ssh_service.delete(wait=True)

    def _to_dict(self):
        res = super()._to_dict()
        if self.body:
            if self.body.get("metadata"):
                res["metadata"] = self.body["metadata"]

            res["spec"] = self.body["spec"]

        if "running" not in res["spec"]:
            res["spec"]["running"] = False

        spec = res["spec"]["template"]["spec"]
        res["spec"]["template"].setdefault("metadata", {}).setdefault(
            "labels", {}
        ).update({"kubevirt.io/vm": self.name, "kubevirt.io/domain": self.name})

        for iface_name in self.interfaces:
            spec.setdefault("domain", {}).setdefault("devices", {}).setdefault(
                "interfaces", []
            ).append({"name": iface_name, "bridge": {}})

        for iface_name, network in self.networks.items():
            spec.setdefault("networks", []).append(
                {"name": iface_name, "multus": {"networkName": network}}
            )

        if self.cloud_init_data:
            cloud_init_volume = {}
            for vol in spec.setdefault("volumes", []):
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
            ] = _generate_cloud_init_user_data(self.cloud_init_data)
            spec.setdefault("domain", {}).setdefault("devices", {}).setdefault(
                "disks", []
            ).append({"disk": {"bus": "virtio"}, "name": "cloudinitdisk"})

        for sa in self.service_accounts:
            spec.setdefault("domain", {}).setdefault("devices", {}).setdefault(
                "disks", []
            ).append({"disk": {}, "name": sa})
            spec.setdefault("volumes", []).append(
                {"name": sa, "serviceAccount": {"serviceAccountName": sa}}
            )

        if self.node_selector:
            spec["nodeSelector"] = {"kubernetes.io/hostname": self.node_selector}

        if self.eviction:
            spec["evictionStrategy"] = "LiveMigrate"

        # cpu settings
        if self.cpu_flags:
            spec.setdefault("domain", {})["cpu"] = self.cpu_flags

        if self.cpu_limits:
            spec.setdefault("domain", {}).setdefault("resources", {}).setdefault(
                "limits", {}
            )
            spec["domain"]["resources"]["limits"].update({"cpu": self.cpu_limits})

        if self.cpu_requests:
            spec.setdefault("domain", {}).setdefault("resources", {}).setdefault(
                "requests", {}
            )
            spec["domain"]["resources"]["requests"].update({"cpu": self.cpu_requests})

        if self.cpu_cores:
            spec.setdefault("domain", {}).setdefault("cpu", {})[
                "cores"
            ] = self.cpu_cores

        if self.cpu_threads:
            spec.setdefault("domain", {}).setdefault("cpu", {})[
                "threads"
            ] = self.cpu_threads

        if self.cpu_sockets:
            spec.setdefault("domain", {}).setdefault("cpu", {})[
                "sockets"
            ] = self.cpu_sockets

        # Memory must be set.
        if self.memory or not self.body:
            spec.setdefault("domain", {}).setdefault("resources", {}).setdefault(
                "requests", {}
            )["memory"] = (self.memory or "64M")

        if self.label:
            res.setdefault("spec", {}).setdefault("template", {}).setdefault(
                "metadata", {}
            ).setdefault("labels", {})["kubevirt.io/vm"] = self.label

        # Create rng device so the vm will able to use /dev/rnd without
        # waiting for entropy collecting.
        res.setdefault("spec", {}).setdefault("template", {}).setdefault(
            "spec", {}
        ).setdefault("domain", {}).setdefault("devices", {}).setdefault("rng", {})

        # image must be set before DV in order to boot from it.
        if self.image:
            spec.setdefault("domain", {}).setdefault("devices", {}).setdefault(
                "disks", []
            ).append({"disk": {"bus": "virtio"}, "name": "containerdisk"})
            spec.setdefault("volumes", []).append(
                {"name": "containerdisk", "containerDisk": {"image": self.image}}
            )

        if self.dv:
            spec.setdefault("domain", {}).setdefault("devices", {}).setdefault(
                "disks", []
            ).append({"disk": {"bus": "virtio"}, "name": "dv-disk"})
            spec.setdefault("volumes", []).append(
                {"name": "dv-disk", "dataVolume": {"name": self.dv}}
            )

        if self.machine_type:
            spec.setdefault("domain", {}).setdefault("machine", {})[
                "type"
            ] = self.machine_type

        return res

    def ssh_enable(self):
        self.ssh_service = SSHServiceForVirtualMachineForTests(
            name=f"ssh-{self.name}", namespace=self.namespace, vm_name=self.name,
        )
        self.ssh_service.create(wait=True)
        self.ssh_node_port = self.ssh_service.instance.attributes.spec.ports[0][
            "nodePort"
        ]


class VirtualMachineForTestsFromTemplate(VirtualMachineForTests):
    def __init__(
        self,
        name,
        namespace,
        client,
        labels,
        template_dv,
        networks=None,
        interfaces=None,
        ssh=False,
    ):
        super().__init__(
            name=name,
            namespace=namespace,
            client=client,
            networks=networks,
            interfaces=interfaces,
            ssh=ssh,
        )
        self.template_labels = labels
        self.template_dv = template_dv

    def _to_dict(self):
        self.body = self.process_template()
        res = super()._to_dict()
        return res

    def process_template(self):
        template_instance = self.get_template_by_labels()
        resources_list = template_instance.process(
            **{"NAME": self.name, "PVCNAME": self.template_dv}
        )
        for resource in resources_list:
            if (
                resource["kind"] == VirtualMachine.kind
                and resource["metadata"]["name"] == self.name
            ):
                # Template have bridge pod network that wont work for migration.
                # Replacing the bridge pod network with masquerade.
                # https://bugzilla.redhat.com/show_bug.cgi?id=1751869
                resource["spec"]["template"]["spec"]["domain"]["devices"][
                    "interfaces"
                ] = [{"masquerade": {}, "name": "default"}]
                return resource

        raise ValueError(f"Template not found for {self.name}")

    def get_template_by_labels(self):
        template = Template.get(
            dyn_client=self.client,
            singular_name=Template.singular_name,
            namespace="openshift",
            label_selector=",".join(
                [f"{label}=true" for label in self.template_labels]
            ),
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


def fedora_vm_body(name):
    return generate_yaml_from_template(
        file_="tests/manifests/vm-fedora.yaml", name=name
    )


def kubernetes_taint_exists(node):
    taints = node.instance.spec.taints
    if taints:
        return any(
            taint.key == K8S_TAINT and taint.effect == NO_SCHEDULE for taint in taints
        )


class SSHServiceForVirtualMachineForTests(Service):
    def __init__(self, name, namespace, vm_name):
        super().__init__(name=name, namespace=namespace)
        self._vm_name = vm_name

    def _to_dict(self):
        res = super()._to_dict()
        res["spec"] = {
            "ports": [{"port": 22, "protocol": "TCP"}],
            "selector": {"kubevirt.io/domain": self._vm_name},
            "sessionAffinity": "None",
            "type": "NodePort",
        }
        return res
