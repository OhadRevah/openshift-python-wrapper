import json
import logging
import os
import random
import re
import shlex
import subprocess
import time
from contextlib import contextmanager

import jinja2
import pexpect
import requests
import utilities.network
import yaml
from pytest_testconfig import config as py_config
from resources.datavolume import DataVolume
from resources.pod import Pod
from resources.resource import ResourceEditor
from resources.route import Route
from resources.secret import Secret
from resources.service import Service
from resources.service_account import ServiceAccount
from resources.sriov_network import SriovNetwork
from resources.template import Template
from resources.utils import TimeoutExpiredError, TimeoutSampler
from resources.virtual_machine import VirtualMachine
from resources.virtual_machine_import import VirtualMachineImport
from rrmngmnt import ssh, user
from utilities import console
from utilities.infra import ClusterHosts


LOGGER = logging.getLogger(__name__)

K8S_TAINT = "node.kubernetes.io/unschedulable"
NO_SCHEDULE = "NoSchedule"
CIRROS_IMAGE = "kubevirt/cirros-container-disk-demo:latest"
FEDORA_CLOUD_INIT_PASSWORD = {
    "userData": {"password": "fedora", "chpasswd": "{ expire: False }"}
}
RHEL_CLOUD_INIT_PASSWORD = {
    "userData": {"password": "redhat", "chpasswd": "{ expire: " "False }"}
}


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


def generate_cloud_init_data(data):
    """
    Generate cloud init data from a dictionary.

    Args:
        data (dict): cloud init data to set under desired section.

    Returns:
        str: A generated str for cloud init.

    Example:
        data = {
            "networkData": {
                "version": 2,
                "ethernets": {
                    "eth0": {
                        "dhcp4": True,
                        "addresses": "[ fd10:0:2::2/120 ]",
                        "gateway6": "fd10:0:2::1",
                    }
                }
            }
        }
        data.update(FEDORA_CLOUD_INIT_PASSWORD)

        with VirtualMachineForTests(
            namespace="namespace",
            name="vm",
            body=fedora_vm_body("vm"),
            cloud_init_data=data,
        ) as vm:
            pass
    """
    dict_data = {}
    for section, _data in data.items():
        str_data = ""
        generated_data = yaml.dump(_data)
        if section == "userData":
            str_data += "#cloud-config\n"

        for line in generated_data.splitlines():
            line = line.replace("'", "")
            str_data += f"{line}\n"
        dict_data[section] = str_data
    return dict_data


def merge_dicts(source_dict, target_dict):
    """ Merge nested source_dict into target_dict """

    for key, value in source_dict.items():
        if isinstance(value, dict):
            node = target_dict.setdefault(key, {})
            merge_dicts(source_dict=value, target_dict=node)
        else:
            target_dict[key] = value

    return target_dict


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
        cloud_init_data=None,
        machine_type=None,
        image=None,
        ssh=False,
        network_model=None,
        network_multiqueue=None,
        pvc=None,
        data_volume=None,
        data_volume_template=None,
        teardown=True,
        cloud_init_type=None,
        attached_secret=None,
        cpu_placement=False,
        smm_enabled=None,
        efi_params=None,
        diskless_vm=False,
    ):
        # Sets VM unique name - replaces "." with "-" in the name to handle valid values.
        self.name = f"{name}-{time.time()}".replace(".", "-")
        super().__init__(
            name=self.name, namespace=namespace, client=client, teardown=teardown
        )
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
        self.cloud_init_data = cloud_init_data
        self.machine_type = machine_type
        self.image = image
        self.ssh = ssh
        self.ssh_service = None
        self.ssh_node_port = None
        self.custom_service = None
        self.custom_service_port = None
        self.network_model = network_model
        self.network_multiqueue = network_multiqueue
        self.data_volume_template = data_volume_template
        self.cloud_init_type = cloud_init_type
        self.pvc = pvc
        self.attached_secret = attached_secret
        self.cpu_placement = cpu_placement
        self.data_volume = data_volume
        self.smm_enabled = smm_enabled
        self.efi_params = efi_params
        self.diskless_vm = diskless_vm

    def __enter__(self):
        super().__enter__()
        if self.ssh:
            self.ssh_enable()
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        super().__exit__(
            exception_type=exception_type,
            exception_value=exception_value,
            traceback=traceback,
        )
        if self.ssh_service:
            self.ssh_service.delete(wait=True)
        if self.custom_service:
            self.custom_service.delete(wait=True)

    def to_dict(self):
        res = super().to_dict()
        if self.body:
            if self.body.get("metadata"):
                # We must set name in Template, since we use a unique name here we override it.
                res["metadata"] = self.body["metadata"]
                res["metadata"]["name"] = self.name

            res["spec"] = self.body["spec"]

        is_vm_from_template = (
            "vm.kubevirt.io/template" in res["metadata"].setdefault("labels", {}).keys()
        )

        if "running" not in res["spec"]:
            res["spec"]["running"] = False

        spec = res["spec"]["template"]["spec"]
        res["spec"]["template"].setdefault("metadata", {}).setdefault(
            "labels", {}
        ).update({"kubevirt.io/vm": self.name, "kubevirt.io/domain": self.name})

        iface_mac_number = random.randint(0, 255)
        for iface_name in self.interfaces:
            try:
                # On cluster without SR-IOV deploy we will get NotImplementedError
                sriov_network_exists = SriovNetwork(
                    name=iface_name,
                    network_namespace=self.namespace,
                    policy_namespace=py_config["sriov_namespace"],
                ).exists
            except NotImplementedError:
                sriov_network_exists = False

            if sriov_network_exists:
                # TODO : Remove hardcoded mac(iface_mac_number) when BZ 1868359 is fixed
                # TODO : JIRA Task :  https://issues.redhat.com/browse/CNV-6349
                spec.setdefault("domain", {}).setdefault("devices", {}).setdefault(
                    "interfaces", []
                ).append(
                    {
                        "name": iface_name,
                        "sriov": {},
                        "macAddress": "02:00:b5:b5:b5:%02x" % (iface_mac_number),
                    }
                )
                iface_mac_number += 1
            else:
                spec.setdefault("domain", {}).setdefault("devices", {}).setdefault(
                    "interfaces", []
                ).append({"name": iface_name, "bridge": {}})

        for iface_name, network in self.networks.items():
            spec.setdefault("networks", []).append(
                {"name": iface_name, "multus": {"networkName": network}}
            )

        if self.network_model:
            spec.setdefault("domain", {}).setdefault("devices", {}).setdefault(
                "interfaces", [{}]
            )[0]["model"] = self.network_model

        if self.network_multiqueue is not None:
            spec.setdefault("domain", {}).setdefault("devices", {}).update(
                {"networkInterfaceMultiqueue": self.network_multiqueue}
            )

        if self.cloud_init_data:
            cloud_init_volume = {}
            for vol in spec.setdefault("volumes", []):
                if vol["name"] == "cloudinitdisk":
                    cloud_init_volume = vol
                    break

            cloud_init_volume_type = self.cloud_init_type or "cloudInitNoCloud"

            if not cloud_init_volume:
                spec["volumes"].append({"name": "cloudinitdisk"})
                cloud_init_volume = spec["volumes"][-1]

            cloud_init_volume[cloud_init_volume_type] = generate_cloud_init_data(
                data=self.cloud_init_data
            )
            disks_spec = (
                spec.setdefault("domain", {})
                .setdefault("devices", {})
                .setdefault("disks", [])
            )

            if not [disk for disk in disks_spec if disk["name"] == "cloudinitdisk"]:
                disks_spec.append({"disk": {"bus": "virtio"}, "name": "cloudinitdisk"})

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

        if self.cpu_placement:
            spec.setdefault("domain", {}).setdefault("cpu", {})[
                "dedicatedCpuPlacement"
            ] = True

        # Memory must be set.
        if self.memory or not self.body:
            spec.setdefault("domain", {}).setdefault("resources", {}).setdefault(
                "requests", {}
            )["memory"] = (self.memory or "64M")

        if self.label:
            # Windows templates are missing spec -> template -> metadata -> labels path
            # https://bugzilla.redhat.com/show_bug.cgi?id=1769692
            # Once fixed, setdefault to 'template' and 'metadata' should be removed.
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

        # DV/PVC info may be taken from self.data_volume_template, self.data_volume or self.pvc
        if self.data_volume_template or self.data_volume or self.pvc:
            storage_class, access_mode, node_selector = self.get_storage_configuration()

            # For storage class that is not ReadWriteMany - evictionStrategy should be removed from the VM
            if DataVolume.AccessMode.RWX not in access_mode:
                spec.pop("evictionStrategy", None)

            # For HPP - DV/PVC and VM must reside on the same node
            if storage_class == "hostpath-provisioner" and not self.node_selector:
                spec["nodeSelector"] = {"kubernetes.io/hostname": node_selector}

            # Needed only for VMs which are not created from common templates
            if not is_vm_from_template:
                if self.pvc:
                    pvc_disk_name = f"{self.pvc.name}-pvc-disk"
                    spec.setdefault("domain", {}).setdefault("devices", {}).setdefault(
                        "disks", []
                    ).append({"disk": {"bus": "virtio"}, "name": pvc_disk_name})
                    spec.setdefault("volumes", []).append(
                        {
                            "name": pvc_disk_name,
                            "persistentVolumeClaim": {"claimName": self.pvc.name},
                        }
                    )
                # self.data_volume / self.data_volume_template
                else:
                    data_volume_name = (
                        self.data_volume.name
                        if self.data_volume
                        else self.data_volume_template["metadata"]["name"]
                    )
                    spec.setdefault("domain", {}).setdefault("devices", {}).setdefault(
                        "disks", []
                    ).append({"disk": {"bus": "virtio"}, "name": "dv-disk"})
                    spec.setdefault("volumes", []).append(
                        {
                            "name": "dv-disk",
                            "dataVolume": {"name": data_volume_name},
                        }
                    )

        if self.data_volume_template:
            res["spec"].setdefault("dataVolumeTemplates", []).append(
                self.data_volume_template
            )

        if self.smm_enabled is not None:
            spec.setdefault("domain", {}).setdefault("features", {}).setdefault(
                "smm", {}
            )["enabled"] = self.smm_enabled

        if self.efi_params is not None:
            spec.setdefault("domain", {}).setdefault("firmware", {}).setdefault(
                "bootloader", {}
            )["efi"] = self.efi_params

        if self.machine_type:
            spec.setdefault("domain", {}).setdefault("machine", {})[
                "type"
            ] = self.machine_type

        if self.attached_secret:
            volume_name = self.attached_secret["volume_name"]
            spec.setdefault("domain", {}).setdefault("devices", {}).setdefault(
                "disks", []
            ).append(
                {
                    "disk": {},
                    "name": volume_name,
                    "serial": self.attached_secret["serial"],
                }
            )
            spec.setdefault("volumes", []).append(
                {
                    "name": volume_name,
                    "secret": {"secretName": self.attached_secret["secret_name"]},
                }
            )

        if self.diskless_vm:
            spec.get("domain", {}).get("devices", {}).pop("disks", None)

        return res

    def ssh_enable(self):
        self.ssh_service = SSHServiceForVirtualMachineForTests(
            name=f"ssh-{self.name}",
            namespace=self.namespace,
            vm_name=self.name,
        )
        self.ssh_service.create(wait=True)
        self.ssh_node_port = self.ssh_service.instance.attributes.spec.ports[0][
            "nodePort"
        ]

    def custom_service_enable(self, service_name, port):
        self.custom_service = CustomServiceForVirtualMachineForTests(
            name=f"{service_name}-{self.name}",
            namespace=self.namespace,
            vm_name=self.name,
            port=port,
        )
        self.custom_service.create(wait=True)
        self.custom_service_port = self.custom_service.instance.attributes.spec.ports[
            0
        ]["nodePort"]

    def get_storage_configuration(self):
        node_annotation = "kubevirt.io/provisionOnNode"
        storage_class = (
            self.data_volume.storage_class
            if self.data_volume
            else self.pvc.instance.spec.storageClassName
            if self.pvc
            else self.data_volume_template["spec"]["pvc"]["storageClassName"]
        )
        access_mode = (
            self.data_volume.instance.spec.pvc.accessModes
            if self.data_volume
            else self.pvc.instance.spec.accessModes
            if self.pvc
            else self.data_volume_template["spec"]["pvc"]["accessModes"]
        )
        node_selector = (
            self.data_volume.pvc.selected_node
            or self.data_volume.pvc.instance.metadata.annotations.get(node_annotation)
            if self.data_volume
            else self.pvc.instance.metadata.annotations.get(node_annotation)
            if self.pvc
            else self.data_volume_template["metadata"]
            .setdefault("annotations", {})
            .get(node_annotation)
        )

        return storage_class, access_mode, node_selector


class VirtualMachineForTestsFromTemplate(VirtualMachineForTests):
    def __init__(
        self,
        name,
        namespace,
        client,
        labels,
        data_volume,
        networks=None,
        interfaces=None,
        ssh=False,
        vm_dict=None,
        cpu_threads=None,
        memory=None,
        network_model=None,
        network_multiqueue=None,
        cloud_init_data=None,
        node_selector=None,
        attached_secret=None,
        termination_grace_period=False,
        diskless_vm=False,
    ):
        super().__init__(
            name=name,
            namespace=namespace,
            client=client,
            networks=networks,
            interfaces=interfaces,
            ssh=ssh,
            network_model=network_model,
            network_multiqueue=network_multiqueue,
            cpu_threads=cpu_threads,
            memory=memory,
            cloud_init_data=cloud_init_data,
            node_selector=node_selector,
            attached_secret=attached_secret,
            data_volume=data_volume,
            diskless_vm=diskless_vm,
        )
        self.template_labels = labels
        self.data_volume = data_volume
        self.vm_dict = vm_dict
        self.cpu_threads = cpu_threads
        self.node_selector = node_selector
        self.termination_grace_period = termination_grace_period

    def to_dict(self):
        self.body = self.process_template()
        res = super().to_dict()

        if self.vm_dict:
            res = merge_dicts(source_dict=self.vm_dict, target_dict=res)

        spec = res["spec"]["template"]["spec"]

        # terminationGracePeriodSeconds for Windows is set to 1hr; this may affect VMI deletion
        # If termination_grace_period == True, do not change the value in the template, else
        # terminationGracePeriodSeconds will be set to 180
        if not self.termination_grace_period:
            spec["terminationGracePeriodSeconds"] = 180

        # TODO: remove once bug 1881658 is resolved
        # The PVC should not have the DV as ownerReferences
        pvc_dict = self.data_volume.pvc.instance.to_dict()
        if pvc_dict["metadata"].get("ownerReferences"):
            pvc_dict["metadata"]["ownerReferences"][0]["kind"] = "PersistentVolumeClaim"
        ResourceEditor(
            {self.data_volume.pvc: {"metadata": pvc_dict["metadata"]}}
        ).update()

        return res

    def process_template(self):
        template_instance = self.get_template_by_labels()
        resources_list = template_instance.process(
            **{"NAME": self.name, "PVCNAME": self.data_volume.name}
        )
        for resource in resources_list:
            if (
                resource["kind"] == VirtualMachine.kind
                and resource["metadata"]["name"] == self.name
            ):
                # Template have bridge pod network that wont work for migration.
                # Replacing the bridge pod network with masquerade.
                # https://bugzilla.redhat.com/show_bug.cgi?id=1751869
                interfaces_dict = resource["spec"]["template"]["spec"]["domain"][
                    "devices"
                ]["interfaces"][0]
                if "bridge" in interfaces_dict:
                    interfaces_dict["masquerade"] = interfaces_dict.pop("bridge")
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

        # TODO: when https://bugzilla.redhat.com/show_bug.cgi?id=1854081 is fixed:
        # 1. Add assert len(list(template)) == 1
        # 2. Remove explicit selection of Windows templates
        if any(re.search(r".*/win.*", label) for label in self.template_labels):
            template = (
                _template
                for _template in template
                if re.match(r"^windows(" r"10)?-.*", _template.name)
            )

        return list(template)[0]


def vm_console_run_commands(
    console_impl, vm, commands, timeout=60, verify_commands_output=True
):
    """
    Run a list of commands inside VM and (if verify_commands_output) check all commands return 0.
    If return code other than 0 then it will break execution and raise exception.

    Args:
        console_impl (Console): Console implementation (RHEL, Fedora, etc)
        vm (obj): VirtualMachine
        commands (list): List of commands
        timeout (int): Time to wait for the command output
        verify_commands_output (book): Check commands return 0
    """
    with console_impl(vm=vm) as vmc:
        for command in commands:
            LOGGER.info(f"Execute {command} on {vm.name}")
            vmc.sendline(command)
            if verify_commands_output:
                vmc.sendline(
                    "echo rc==$?=="
                )  # This construction rc==$?== is unique. Return code validation
                try:
                    vmc.expect("rc==0==", timeout=timeout)  # Expected return code is 0
                except pexpect.exceptions.TIMEOUT:
                    raise CommandExecFailed(command)
            else:
                vmc.expect(".*")


class CommandExecFailed(Exception):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"Command: {self.name} - exec failed."


def run_command(command):
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
    return run_command(command=virtctl_cmd)


def fedora_vm_body(name):
    from pkg_resources import resource_stream

    # Make sure we can find the file even if utilities was installed via pip.
    yaml_file = resource_stream("utilities", "manifests/vm-fedora.yaml").name
    return generate_yaml_from_template(file_=yaml_file, name=name)


def kubernetes_taint_exists(node):
    taints = node.instance.spec.taints
    if taints:
        return any(
            taint.key == K8S_TAINT and taint.effect == NO_SCHEDULE for taint in taints
        )


class SSHServiceForVirtualMachineForTests(Service):
    def __init__(self, name, namespace, vm_name, teardown=True):
        super().__init__(name=name, namespace=namespace, teardown=teardown)
        self._vm_name = vm_name

    def to_dict(self):
        res = super().to_dict()
        res["spec"] = {
            "ports": [{"port": 22, "protocol": "TCP"}],
            "selector": {"kubevirt.io/domain": self._vm_name},
            "sessionAffinity": "None",
            "type": "NodePort",
        }
        return res


class CustomServiceForVirtualMachineForTests(Service):
    def __init__(self, name, namespace, vm_name, port, teardown=True):
        super().__init__(name=name, namespace=namespace, teardown=teardown)
        self._vm_name = vm_name
        self.port = port

    def to_dict(self):
        res = super().to_dict()
        res["spec"] = {
            "ports": [{"port": self.port, "protocol": "TCP"}],
            "selector": {"kubevirt.io/domain": self._vm_name},
            "sessionAffinity": "None",
            "type": "NodePort",
        }
        return res


class Prometheus(object):
    """
    For accessing Prometheus cluster metrics

    Prometheus HTTP API doc:
    https://prometheus.io/docs/prometheus/latest/querying/api/

    Argument for query method should be the entire string following the server address
        e.g.
        prometheus = Prometheus()
        up = prometheus.query("/api/v1/query?query=up")
    """

    def __init__(self):
        self.namespace = "openshift-monitoring"
        self.resource_name = "prometheus-k8s"

        # get route to prometheus HTTP api
        self.api_url = self._get_route()

        # get prometheus ServiceAccount token
        self.headers = self._get_headers()

    def _get_route(self):
        # get route to prometheus HTTP api
        LOGGER.info("Prometheus: Obtaining route")
        route = Route(
            namespace=self.namespace, name=self.resource_name
        ).instance.spec.host

        return f"https://{route}"

    def _get_headers(self):
        """Uses the Prometheus serviceaccount to get an access token for OAuth"""
        LOGGER.info("Prometheus: Setting headers")

        LOGGER.info("Prometheus headers: Obtaining OAuth token")

        # get SA
        prometheus_sa = ServiceAccount(
            namespace=self.namespace, name=self.resource_name
        )

        # get secret
        secret_name = prometheus_sa.instance.imagePullSecrets[0].name
        secret = Secret(namespace=self.namespace, name=secret_name)

        # get token value
        token = secret.instance.metadata.annotations["openshift.io/token-secret.value"]

        return {"Authorization": f"Bearer {token}"}

    def query(self, query):
        response = requests.get(
            f"{self.api_url}/{query}", headers=self.headers, verify=False
        )

        # parse json response and return as dict
        return json.loads(response.content)


def enable_ssh_service_in_vm(vm, console_impl, systemctl_support=True):
    LOGGER.info("Enable SSH in VM.")

    enable_ssh_command = [
        r"sudo sed -iE "
        r"'s/^#\?PasswordAuthentication no/PasswordAuthentication yes/g'"
        r" /etc/ssh/sshd_config",
    ]

    vm_console_run_commands(
        console_impl=console_impl,
        vm=vm,
        commands=enable_ssh_command,
    )

    if systemctl_support:
        ssh_service_restart_cmd = ["sudo systemctl restart sshd"]
    # For older linux versions which do not support systemctl
    else:
        ssh_service_restart_cmd = ["sudo /etc/init.d/sshd restart"]

    vm_console_run_commands(
        console_impl=console_impl,
        vm=vm,
        commands=ssh_service_restart_cmd,
        verify_commands_output=False,
    )

    # RHEL 7-7 has issue with running "sudo systemctl" command and disconnecting right after it
    if "7.7" in vm.vmi.os_version:
        console_impl(vm=vm).force_disconnect()

    wait_for_ssh_service(
        vm=vm, console_impl=console_impl, systemctl_support=systemctl_support
    )


def wait_for_ssh_service(vm, console_impl, systemctl_support=True):
    LOGGER.info("Wait for SSH service to be active.")

    sampler = TimeoutSampler(
        timeout=30,
        sleep=5,
        func=ssh_service_activated,
        exceptions=(pexpect.exceptions.TIMEOUT, pexpect.exceptions.EOF),
        vm=vm,
        console_impl=console_impl,
        systemctl_support=systemctl_support,
    )
    for sample in sampler:
        if sample:
            return


def ssh_service_activated(vm, console_impl, systemctl_support=True):
    if systemctl_support:
        ssh_service_status_cmd = "sudo systemctl is-active sshd"
        expected = "\r\nactive"
    else:
        ssh_service_status_cmd = "sudo /etc/init.d/sshd status"
        expected = "is running"

    with console_impl(vm=vm) as vm_console:
        vm_console.sendline(ssh_service_status_cmd)
        vm_console.expect(expected)
        return True


def wait_for_console(vm, console_impl):
    with console_impl(vm=vm, timeout=1500):
        pass


def generate_yaml_from_template(file_, **kwargs):
    """
    Generate JSON from yaml file_

    Args:
        file_ (str): Yaml file

    Keyword Args:
        name (str):
        image (str):

    Returns:
        dict: Generated from template file

    Raises:
        MissingTemplateVariables: If not all template variables exists

    Examples:
        generate_yaml_from_template(file_='path/to/file/name', name='vm-name-1')
    """
    with open(file_, "r") as stream:
        data = stream.read()

    # Find all template variables
    template_vars = [i.split()[1] for i in re.findall(r"{{ .* }}", data)]
    for var in template_vars:
        if var not in kwargs.keys():
            raise MissingTemplateVariables(var=var, template=file_)
    template = jinja2.Template(data)
    out = template.render(**kwargs)
    return yaml.safe_load(out)


class MissingTemplateVariables(Exception):
    def __init__(self, var, template):
        self.var = var
        self.template = template

    def __str__(self):
        return f"Missing variables {self.var} for template {self.template}"


def validate_windows_guest_agent_info(vm, winrmcli_pod, helper_vm=False):
    """ Compare guest OS info from VMI (reported by guest agent) and from OS itself. """
    windown_os_info_from_rmcli = get_windows_os_info_from_rmcli(
        vm=vm, winrmcli_pod=winrmcli_pod, helper_vm=helper_vm
    )
    for key, val in get_guest_os_info_from_vmi(vmi=vm.vmi).items():
        if key != "id":
            assert (
                val.split("r")[0]
                if "version" in key
                else val in windown_os_info_from_rmcli
            )


def get_guest_os_info_from_vmi(vmi):
    """ Gets guest OS info from VMI. """
    guest_os_info_dict = dict(vmi.instance.status.guestOSInfo)
    assert guest_os_info_dict, "Guest agent not installed/active."
    return guest_os_info_dict


def get_windows_os_info_from_rmcli(vm, winrmcli_pod, helper_vm=False):
    """
    Gets Windows OS info via remote cli tool from systeminfo.
    Return string of OS Name and OS Version output of systeminfo.
    """
    return execute_winrm_cmd(
        vmi_ip=vm.vmi.virt_launcher_pod.instance.status.podIP,
        winrmcli_pod=winrmcli_pod,
        cmd='systeminfo | findstr /B /C:"OS Name" /C:"OS Version"',
        target_vm=vm,
        helper_vm=helper_vm,
    )


def execute_winrm_cmd(
    vmi_ip, winrmcli_pod, cmd, timeout=120, target_vm=False, helper_vm=False
):
    """
    For RHEL7 workers, pass in the following:
    target_vm: vm which the command will be executed on
    helper_vm: cmd execution is done using a helper vm, must be fedora
    """
    if helper_vm:
        LOGGER.info(f"Running {cmd} via helper VM.")
        return execute_winrm_in_vm(target_vm=target_vm, helper_vm=helper_vm, cmd=cmd)
    else:
        LOGGER.info(f"Running {cmd} via winrm pod.")

        winrmcli_cmd = [
            "bash",
            "-c",
            f"/bin/winrm-cli -hostname {vmi_ip} \
            -username {py_config['windows_username']} -password {py_config['windows_password']} \
            \"{cmd}\"",
        ]
        return winrmcli_pod.execute(command=winrmcli_cmd, timeout=timeout)


def execute_winrm_in_vm(target_vm, helper_vm, cmd):
    target_vm_ip = utilities.network.get_vmi_ip_v4_by_name(
        vmi=target_vm.vmi, name=[*target_vm.networks][0]
    )

    run_cmd = shlex.split(
        f"podman run -it docker.io/kubevirt/winrmcli winrm-cli -hostname "
        f"{target_vm_ip} -username {py_config['windows_username']} -password "
        f"{py_config['windows_password']}"
    ) + [cmd]

    return execute_ssh_command(
        username=console.Fedora.USERNAME,
        passwd=console.Fedora.PASSWORD,
        ip=utilities.network.get_vmi_ip_v4_by_name(
            vmi=helper_vm.vmi, name=[*helper_vm.networks][0]
        ),
        port=22,
        cmd=run_cmd,
        timeout=480,
    )


def execute_ssh_command(username, passwd, ip, port, cmd, timeout=60):
    ssh_user = user.User(name=username, password=passwd)
    rc, out, err = ssh.RemoteExecutor(
        user=ssh_user, address=str(ip), port=port
    ).run_cmd(cmd=cmd, tcp_timeout=timeout, io_timeout=timeout)
    assert rc == 0 and not err, f"SSH command {' '.join(cmd)} failed!"
    return out


def wait_for_windows_vm(vm, version, winrmcli_pod, timeout=1500, helper_vm=False):
    """
    Samples Windows VM; wait for it to complete the boot process.
    """

    LOGGER.info(
        f"Windows VM {vm.name} booting up, "
        f"will attempt to access it up to 25 minutes."
    )

    sampler = TimeoutSampler(
        timeout=timeout,
        sleep=15,
        func=execute_winrm_cmd,
        vmi_ip=vm.vmi.virt_launcher_pod.instance.status.podIP,
        winrmcli_pod=winrmcli_pod,
        target_vm=vm,
        helper_vm=helper_vm,
        cmd="wmic os get Caption /value",
    )
    for sample in sampler:
        if version in str(sample):
            return True


class WinRMcliPod(Pod):
    def __init__(self, name, namespace, node_selector=None, teardown=True):
        super().__init__(name=name, namespace=namespace, teardown=teardown)
        self.node_selector = node_selector

    def to_dict(self):
        res = super().to_dict()
        res["spec"] = {
            "containers": [
                {
                    "name": "winrmcli-con",
                    "image": "kubevirt/winrmcli:latest",
                    "command": ["bash", "-c", "/usr/bin/sleep 6000"],
                }
            ]
        }
        if self.node_selector:
            res["spec"]["nodeSelector"] = {"kubernetes.io/hostname": self.node_selector}

        return res


def nmcli_add_con_cmds(workers_type, iface, ip, default_gw, dns_server):
    bootcmds = [f"nmcli con add type ethernet con-name {iface} ifname {iface}"]

    # On bare metal cluster, address is acquired by DHCP
    # Default GW is set to eth1, thus should be removed from eth0
    if workers_type == ClusterHosts.Type.PHYSICAL:
        bootcmds += [
            "nmcli connection modify eth1 ipv4.method auto",
            "route del default gw  0.0.0.0 eth0",
        ]
    else:
        bootcmds += [
            f"nmcli con mod {iface} ipv4.addresses {ip}/24 "
            f"ipv4.method manual connection.autoconnect-priority 1 ipv6.method ignore"
        ]
    bootcmds += [f"nmcli con up {iface}"]

    # On PSI, change default GW to brcnv network
    if workers_type == ClusterHosts.Type.VIRTUAL:
        bootcmds += [
            f"ip route replace default via " f"{default_gw}",
            "route del default gw  0.0.0.0 eth0",
            f"bash -c 'echo \"nameserver " f'{dns_server}" ' f">/etc/resolv.conf'",
        ]

    return bootcmds


def check_ssh_connection(ip, port, console_impl):
    """Verifies successful SSH connection
    Args:
        ip (str): host IP
        port (int): host port

    Returns:
        bool: True if connection succeeds else False
    """

    LOGGER.info("Check SSH connection to VM.")

    ssh_user = user.User(
        name=console_impl.USERNAME,
        password=console_impl.PASSWORD,
    )
    return ssh.RemoteExecutor(
        user=ssh_user, address=str(ip), port=port
    ).wait_for_connectivity_state(
        positive=True,
        timeout=120,
        tcp_connection_timeout=120,
    )


@contextmanager
def create_vm_import(
    name,
    namespace,
    provider_credentials_secret_name,
    provider_credentials_secret_namespace,
    target_vm_name,
    vm_id=None,
    vm_name=None,
    cluster_name=None,
    ovirt_mappings=None,
    start_vm=False,
):
    with VirtualMachineImport(
        name=name,
        namespace=namespace,
        provider_credentials_secret_name=provider_credentials_secret_name,
        provider_credentials_secret_namespace=provider_credentials_secret_namespace,
        vm_id=vm_id,
        target_vm_name=target_vm_name,
        start_vm=start_vm,
        ovirt_mappings=ovirt_mappings,
        vm_name=vm_name,
        cluster_name=cluster_name,
    ) as vmimport:
        yield vmimport
