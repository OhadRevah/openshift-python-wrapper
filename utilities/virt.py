import ipaddress
import json
import logging
import os
import re
import shlex
import subprocess
import time
from contextlib import contextmanager

import jinja2
import pexpect
import requests
import rrmngmnt
import yaml
from ocp_resources.datavolume import DataVolume
from ocp_resources.route import Route
from ocp_resources.secret import Secret
from ocp_resources.service import Service
from ocp_resources.service_account import ServiceAccount
from ocp_resources.template import Template
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from ocp_resources.virtual_machine import (
    VirtualMachine,
    VirtualMachineInstanceMigration,
)
from ocp_resources.virtual_machine_import import VirtualMachineImport
from pytest_testconfig import config as py_config

import utilities.network
from utilities.constants import (
    CLOUD_INIT_DISK_NAME,
    CLOUD_INIT_NO_CLOUD,
    CNV_SSH_KEY_PATH,
    IP_FAMILY_POLICY_PREFER_DUAL_STACK,
    OS_FLAVOR_CIRROS,
    OS_FLAVOR_FEDORA,
    OS_FLAVOR_WINDOWS,
    OS_LOGIN_PARAMS,
    TIMEOUT_4MIN,
)
from utilities.exceptions import CommandExecFailed
from utilities.infra import (
    BUG_STATUS_CLOSED,
    ClusterHosts,
    camelcase_to_mixedcase,
    get_admin_client,
    get_bug_status,
    get_bugzilla_connection_params,
    get_schedulable_nodes_ips,
    private_to_public_key,
    run_ssh_commands,
)


LOGGER = logging.getLogger(__name__)

K8S_TAINT = "node.kubernetes.io/unschedulable"
NO_SCHEDULE = "NoSchedule"
CIRROS_IMAGE = "kubevirt/cirros-container-disk-demo:latest"

FEDORA_LOGIN_PARAMS = OS_LOGIN_PARAMS["fedora"]
FEDORA_CLOUD_INIT_PASSWORD = {
    "userData": {
        "user": FEDORA_LOGIN_PARAMS["username"],
        "password": FEDORA_LOGIN_PARAMS["password"],
        "chpasswd": "{ expire: False }",
    }
}
RHEL_LOGIN_PARAMS = OS_LOGIN_PARAMS["rhel"]
RHEL_CLOUD_INIT_PASSWORD = {
    "userData": {
        "user": RHEL_LOGIN_PARAMS["username"],
        "password": RHEL_LOGIN_PARAMS["password"],
        "chpasswd": "{ expire: False }",
    }
}
FLAVORS_EXCLUDED_FROM_CLOUD_INIT = (OS_FLAVOR_WINDOWS, OS_FLAVOR_CIRROS)


def wait_for_guest_agent(vmi, timeout=720):
    LOGGER.info(f"Wait until guest agent is active on {vmi.name}")

    sampler = TimeoutSampler(wait_timeout=timeout, sleep=1, func=lambda: vmi.instance)
    try:
        for sample in sampler:
            agent_status = [
                condition
                for condition in sample.get("status", {}).get("conditions", {})
                if condition.get("type") == "AgentConnected"
                and condition.get("status") == "True"
            ]
            if agent_status:
                return True

    except TimeoutExpiredError:
        LOGGER.error(f"Guest agent is not installed or not active on {vmi.name}")
        if (
            get_bug_status(
                bugzilla_connection_params=get_bugzilla_connection_params(), bug=1945703
            )
            not in BUG_STATUS_CLOSED
        ):
            LOGGER.error(
                "Due to bug 1945703 guest agent may not report its status and VM interfaces may not be available."
            )
        else:
            raise


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
    # TODO: remove the if once bug 1945703 is fixed
    if wait_for_guest_agent(vmi=vmi, timeout=timeout):
        LOGGER.info(f"Wait for {vmi.name} network interfaces")
        sampler = TimeoutSampler(
            wait_timeout=timeout, sleep=1, func=lambda: vmi.instance
        )
        for sample in sampler:
            interfaces = sample.get("status", {}).get("interfaces", [])
            active_interfaces = [
                interface
                for interface in interfaces
                if interface.get("ipAddress") and interface.get("interfaceName")
            ]
            if len(active_interfaces) == len(interfaces):
                return True


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
        generated_data = yaml.dump(_data, width=1000)
        if section == "userData":
            str_data += "#cloud-config\n"

        for line in generated_data.splitlines():
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
        eviction=False,
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
        cpu_model=None,
        memory_requests=None,
        memory_limits=None,
        memory_guest=None,
        cloud_init_data=None,
        machine_type=None,
        image=None,
        ssh=True,
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
        running=False,
        run_strategy=None,
        disk_io_options=None,
        rhel7_workers=False,
        username=None,
        password=None,
        macs=None,
        interfaces_types=None,
        os_flavor=OS_FLAVOR_FEDORA,
        host_device_name=None,
        gpu_name=None,
        systemctl_support=True,
    ):
        """
        Virtual machine creation

        Args:
            name (str): VM name
            namespace (str): Namespace name
            body (dict, optional): VM [metadata] and spec
            eviction (bool, default False): If True, set evictionStrategy to LiveMigrate
            client (:obj:`DynamicClient`, optional): admin client or unprivileged client
            interfaces (list, optional): list of interfaces names
            networks (dict, optional)
            node_selector (str, optional): Node name
            service_accounts (list, optional): list of service account names
            cpu_flags (str, optional)
            cpu_limits (quantity, optional): quantity supports string, ints, and floats
            cpu_requests (quantity, optional): quantity supports string, ints, and floats
            cpu_sockets (int, optional)
            cpu_cores (int, optional)
            cpu_threads (int, optional)
            cpu_model (str, optional)
            memory_requests (str, optional)
            memory_limits (str, optional)
            memory_guest (str, optional)
            cloud_init_data (dict, optional): cloud-init dict
            machine_type (str, optional)
            image (str, optional)
            ssh (bool, default: True): If True and using "with" (contextmanager) statement, create an SSH service
            network_model (str, optional)
            network_multiqueue (None/bool, optional, default: None): If not None, set to True/False
            pvc (:obj:`PersistentVolumeClaim`, optional)
            data_volume (:obj:`DataVolume`, optional)
            data_volume_template (dict, optional)
            teardown (bool, default: True)
            cloud_init_type (str, optional): cloud-init type, for example: cloudInitNoCloud
            attached_secret (dict, optional)
            cpu_placement (bool, default: False): If True, set dedicatedCpuPlacement = True
            smm_enabled (None/bool, optional, default: None): If not None, set to True/False
            efi_params (dict, optional)
            diskless_vm (bool, default: False): If True, remove VM disks
            running (bool, default: False): If True, running = True
            run_strategy (str, optional): Set runStrategy (run_strategy and running are mutually exclusive)
            disk_io_options (str, optional): Set root disk IO
            rhel7_workers (bool, default: False)
            username (str, optional): SSH username
            password (str, optional): SSH password
            macs (dict, optional): Dict of {interface_name: mac address}
            interfaces_types (dict, optional): Dict of interfaces names and type ({"iface1": "sriov"})
            os_flavor (str, default: fedora): OS flavor to get SSH login parameters.
                (flavor should be exist in constants.py)
            host_device_name (str, optional): PCI Host Device Name (For Example: "nvidia.com/GV100GL_Tesla_V100")
            gpu_name (str, optional): GPU Device Name (For Example: "nvidia.com/GV100GL_Tesla_V100")
            systemctl_support(bool, default=True): whether OS supports systemctl (RHEL 6 does not)
        """
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
        self.cpu_model = cpu_model
        self.memory_requests = memory_requests
        self.memory_limits = memory_limits
        self.memory_guest = memory_guest
        self.cloud_init_data = cloud_init_data
        self.machine_type = machine_type
        self.image = image
        self.ssh = ssh
        self.ssh_service = None
        self.custom_service = None
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
        self.is_vm_from_template = False
        self.running = running
        self.run_strategy = run_strategy
        self.disk_io_options = disk_io_options
        self.username = username
        self.password = password
        self.rhel7_workers = rhel7_workers
        self.macs = macs
        self.interfaces_types = interfaces_types or {}
        self.os_flavor = os_flavor
        self.host_device_name = host_device_name
        self.gpu_name = gpu_name
        self.systemctl_support = systemctl_support

    def deploy(self):
        super().deploy()
        if self.ssh:
            self.ssh_enable()
        return self

    def clean_up(self):
        super().clean_up()
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

        self.is_vm_from_template = (
            "vm.kubevirt.io/template" in res["metadata"].setdefault("labels", {}).keys()
        )

        # runStrategy and running are mutually exclusive
        #
        # From RunStrategy() in
        # https://github.com/kubevirt/kubevirt/blob/master/staging/src/kubevirt.io/client-go/api/v1/types.go
        # if vm.spec.running is set, that will be mapped to runStrategy:
        #   false: RunStrategyHalted
        #   true: RunStrategyAlways
        #
        # To create a VM resource, but not begin VM cloning, use VirtualMachine.RunStrategy.MANUAL
        if self.run_strategy:
            res["spec"].pop("running", None)
            res["spec"]["runStrategy"] = self.run_strategy
        else:
            res["spec"]["running"] = self.running

        spec = res["spec"]["template"]["spec"]
        res["spec"]["template"].setdefault("metadata", {}).setdefault(
            "labels", {}
        ).update({"kubevirt.io/vm": self.name, "kubevirt.io/domain": self.name})

        spec = self.update_vm_network_configuration(spec=spec)
        spec = self.update_vm_cpu_configuration(spec=spec)
        spec = self.update_vm_memory_configuration(spec=spec)

        for sa in self.service_accounts:
            spec.setdefault("domain", {}).setdefault("devices", {}).setdefault(
                "disks", []
            ).append({"disk": {}, "name": sa})
            spec.setdefault("volumes", []).append(
                {"name": sa, "serviceAccount": {"serviceAccountName": sa}}
            )

        # Create rng device so the vm will able to use /dev/rnd without
        # waiting for entropy collecting.
        res.setdefault("spec", {}).setdefault("template", {}).setdefault(
            "spec", {}
        ).setdefault("domain", {}).setdefault("devices", {}).setdefault("rng", {})

        res, spec = self.update_vm_storage_configuration(res=res, spec=spec)

        if self.cloud_init_data:
            spec = self.update_vm_cloud_init_data(spec=spec)

        # VMs do not necessarily have self.cloud_init_data
        if self.ssh and self.os_flavor not in FLAVORS_EXCLUDED_FROM_CLOUD_INIT:
            spec = self.enable_ssh_in_cloud_init_data(spec=spec)

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
            spec = self.update_vm_secret_configuration(spec=spec)

        if self.diskless_vm:
            spec.get("domain", {}).get("devices", {}).pop("disks", None)

        if self.host_device_name:
            spec.setdefault("domain", {}).setdefault("devices", {}).setdefault(
                "hostDevices", []
            ).append(
                {
                    "deviceName": self.host_device_name,
                    "name": "hostdevice",
                }
            )

        if self.gpu_name:
            spec.setdefault("domain", {}).setdefault("devices", {}).setdefault(
                "gpus", []
            ).append(
                {
                    "deviceName": self.gpu_name,
                    "name": "gpu",
                }
            )

        if self.disk_io_options:
            disks_spec = (
                spec.setdefault("domain", {})
                .setdefault("devices", {})
                .setdefault("disks", [])
            )
            # In VM from template, rootdisk is named as the VM name
            disk_name = self.name if self.is_vm_from_template else "rootdisk"
            for disk in disks_spec:
                if disk["name"] == disk_name:
                    disk["io"] = self.disk_io_options
                    break
        return res

    def update_vm_memory_configuration(self, spec):
        if self.memory_requests:
            spec.setdefault("domain", {}).setdefault("resources", {}).setdefault(
                "requests", {}
            )["memory"] = self.memory_requests

        if self.memory_limits:
            spec.setdefault("domain", {}).setdefault("resources", {}).setdefault(
                "limits", {}
            )["memory"] = self.memory_limits

        if self.memory_guest:
            spec.setdefault("domain", {}).setdefault("memory", {})[
                "guest"
            ] = self.memory_guest

        return spec

    def update_vm_network_configuration(self, spec):
        for iface_name in self.interfaces:
            iface_type = self.interfaces_types.get(iface_name, "bridge")
            network_dict = {"name": iface_name, iface_type: {}}

            if self.macs:
                network_dict["macAddress"] = self.macs.get(iface_name)

            spec.setdefault("domain", {}).setdefault("devices", {}).setdefault(
                "interfaces", []
            ).append(network_dict)

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

        return spec

    def update_vm_cloud_init_data(self, spec):
        cloud_init_volume = vm_cloud_init_volume(vm_spec=spec)
        cloud_init_volume_type = self.cloud_init_type or CLOUD_INIT_NO_CLOUD

        cloud_init_volume[cloud_init_volume_type] = generate_cloud_init_data(
            data=self.cloud_init_data
        )
        disks_spec = (
            spec.setdefault("domain", {})
            .setdefault("devices", {})
            .setdefault("disks", [])
        )

        if not [disk for disk in disks_spec if disk["name"] == CLOUD_INIT_DISK_NAME]:
            disks_spec.append({"disk": {"bus": "virtio"}, "name": CLOUD_INIT_DISK_NAME})

        return spec

    def enable_ssh_in_cloud_init_data(self, spec):
        cloud_init_volume = vm_cloud_init_volume(vm_spec=spec)
        cloud_init_volume_type = self.cloud_init_type or CLOUD_INIT_NO_CLOUD

        cloud_init_volume.setdefault(cloud_init_volume_type, {}).setdefault(
            "userData", ""
        )

        # Saving in an intermediate string for readability
        cloud_init_user_data = cloud_init_volume[cloud_init_volume_type]["userData"]

        # Add RSA to authorized_keys to enable login using an SSH key
        authorized_key = (
            f"ssh-rsa {private_to_public_key(key=CNV_SSH_KEY_PATH)} root@exec1.rdocloud"
        )
        cloud_init_user_data += f"\nssh_authorized_keys:\n [{authorized_key}]"

        # Add ssh-rsa to opensshserver.config PubkeyAcceptedKeyTypes - needed when using SSH via paramiko
        # Enable PasswordAuthentication in /etc/ssh/sshd_config
        # Enable SSH service and restart SSH service
        run_cmd_commands = [
            (
                "sudo sed -i '/^PubkeyAcceptedKeyTypes/ s/$/,ssh-rsa/' "
                "/etc/crypto-policies/back-ends/opensshserver.config"
            ),
            (
                r"sudo sed -i 's/^#\?PasswordAuthentication no/PasswordAuthentication yes/g' "
                "/etc/ssh/sshd_config"
            ),
            "sudo systemctl enable sshd" if self.systemctl_support else "",
            (
                "sudo systemctl restart sshd"
                if self.systemctl_support
                else "sudo /etc/init.d/sshd restart"
            ),
        ]

        run_ssh_generated_data = generate_cloud_init_data(
            data={"runcmd": run_cmd_commands}
        )

        # If runcmd already exists in userData, add run_cmd_commands before any other command
        runcmd_prefix = "runcmd:"
        if runcmd_prefix in cloud_init_user_data:
            cloud_init_user_data = re.sub(
                runcmd_prefix,
                f"{runcmd_prefix}\n{run_ssh_generated_data['runcmd']}",
                cloud_init_user_data,
            )
        else:
            cloud_init_user_data += f"\nruncmd: {run_cmd_commands}"

        cloud_init_volume[cloud_init_volume_type]["userData"] = cloud_init_user_data

        return spec

    def update_vm_cpu_configuration(self, spec):
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

        if self.cpu_model:
            spec.setdefault("domain", {}).setdefault("cpu", {})[
                "model"
            ] = self.cpu_model

        return spec

    def update_vm_storage_configuration(self, res, spec):
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
            storage_class, access_mode = self.get_storage_configuration()

            # For storage class that is not ReadWriteMany - evictionStrategy should be removed from the VM
            if DataVolume.AccessMode.RWX not in access_mode:
                spec.pop("evictionStrategy", None)

            # Needed only for VMs which are not created from common templates
            if not self.is_vm_from_template:
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

        return res, spec

    def update_vm_secret_configuration(self, spec):
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

        return spec

    def ssh_enable(self):
        # To use the service: ssh_service.service_ip() and ssh_service.service_port
        # Name is restricted to 63 characters
        self.ssh_service = ServiceForVirtualMachineForTests(
            name=f"ssh-{self.name}"[:63],
            namespace=self.namespace,
            vm=self,
            port=22,
            service_type=Service.Type.NODE_PORT,
            rhel7_workers=self.rhel7_workers,
        )
        self.ssh_service.create(wait=True)

    def custom_service_enable(
        self,
        service_name,
        port,
        service_type=None,
        service_ip=None,
        ip_family_policy=None,
        ip_families=None,
    ):
        """
        service_type is set with K8S default service type (ClusterIP)
        service_ip - relevant for node port; default will be set to vm node IP
        ip_families - list of IP families to be supported in the service (IPv4/6 or both)
        ip_family_policy - SingleStack, RequireDualStack or PreferDualStack
        To use the service: custom_service.service_ip() and custom_service.service_port
        """
        self.custom_service = ServiceForVirtualMachineForTests(
            name=f"{service_name}-{self.name}"[:63],
            namespace=self.namespace,
            vm=self,
            port=port,
            service_type=service_type,
            target_ip=service_ip,
            ip_family_policy=ip_family_policy,
            ip_families=ip_families,
        )
        self.custom_service.create(wait=True)

    def get_storage_configuration(self):
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

        return storage_class, access_mode

    @property
    def ssh_exec(self):
        # In order to use this property VM should be created with ssh=True
        # or one of vm_ssh_service_*** (compute/ssp/supported_os/conftest.py) fixtures should be used
        login_params = OS_LOGIN_PARAMS[self.os_flavor]
        self.username = self.username or login_params["username"]
        self.password = self.password or login_params["password"]

        LOGGER.info(
            f"Username: {self.username}, password: {self.password}, SSH key: {CNV_SSH_KEY_PATH} "
            f"ssh {self.username}@{self.ssh_service.service_ip()} -p {self.ssh_service.service_port}"
        )
        host = rrmngmnt.Host(ip=str(self.ssh_service.service_ip()))
        # For SSH using a key, the public key needs to reside on the server.
        # As the tests use a given set of credentials, this cannot be done in Windows/Cirros.
        if self.os_flavor in FLAVORS_EXCLUDED_FROM_CLOUD_INIT:
            host_user = rrmngmnt.user.User(name=self.username, password=self.password)
        else:
            host_user = rrmngmnt.user.UserWithPKey(
                name=self.username, private_key=CNV_SSH_KEY_PATH
            )
        host.executor_user = host_user
        host.executor_factory = rrmngmnt.ssh.RemoteExecutorFactory(
            port=self.ssh_service.service_port
        )
        return host


class VirtualMachineForTestsFromTemplate(VirtualMachineForTests):
    def __init__(
        self,
        name,
        namespace,
        client,
        labels,
        data_volume=None,
        data_volume_template=None,
        existing_data_volume=None,
        networks=None,
        interfaces=None,
        ssh=True,
        vm_dict=None,
        cpu_cores=None,
        cpu_threads=None,
        cpu_model=None,
        cpu_flags=None,
        memory_requests=None,
        network_model=None,
        network_multiqueue=None,
        cloud_init_data=None,
        node_selector=None,
        attached_secret=None,
        termination_grace_period=180,
        diskless_vm=False,
        run_strategy=None,
        disk_options_vm=None,
        smm_enabled=None,
        efi_params=None,
        rhel7_workers=False,
        macs=None,
        interfaces_types=None,
        host_device_name=None,
        gpu_name=None,
        cloned_dv_size=None,
        systemctl_support=True,
    ):
        """
        VM creation using common templates.

        Args:
            data_volume (obj `DataVolume`): DV object that will be cloned into a VM PVC
            data_volume_template (dict): dataVolumeTemplates dict to replace template's default dataVolumeTemplates
            existing_data_volume (obj `DataVolume`): An existing DV object that will be used as the VM's volume. Cloning
                will not be done and the template's dataVolumeTemplates will be removed.

        Returns:
            obj `VirtualMachine`: VM resource
        """
        super().__init__(
            name=name,
            namespace=namespace,
            client=client,
            networks=networks,
            interfaces=interfaces,
            ssh=ssh,
            network_model=network_model,
            network_multiqueue=network_multiqueue,
            cpu_cores=cpu_cores,
            cpu_threads=cpu_threads,
            cpu_model=cpu_model,
            cpu_flags=cpu_flags,
            memory_requests=memory_requests,
            cloud_init_data=cloud_init_data,
            node_selector=node_selector,
            attached_secret=attached_secret,
            data_volume=data_volume,
            data_volume_template=data_volume_template,
            diskless_vm=diskless_vm,
            run_strategy=run_strategy,
            disk_io_options=disk_options_vm,
            smm_enabled=smm_enabled,
            efi_params=efi_params,
            rhel7_workers=rhel7_workers,
            macs=macs,
            interfaces_types=interfaces_types,
            host_device_name=host_device_name,
            gpu_name=gpu_name,
            systemctl_support=systemctl_support,
        )
        self.template_labels = labels
        self.data_volume = data_volume
        self.data_volume_template = data_volume_template
        self.existing_data_volume = existing_data_volume
        self.vm_dict = vm_dict
        self.cpu_threads = cpu_threads
        self.node_selector = node_selector
        self.termination_grace_period = termination_grace_period
        self.cloud_init_data = cloud_init_data
        self.cloned_dv_size = cloned_dv_size

    def to_dict(self):
        self.os_flavor = self._extract_os_from_template()
        self.body = self.process_template()
        res = super().to_dict()

        if self.vm_dict:
            res = merge_dicts(source_dict=self.vm_dict, target_dict=res)

        spec = res["spec"]["template"]["spec"]

        # terminationGracePeriodSeconds for Windows is set to 1hr; this may affect VMI deletion
        # If termination_grace_period is not provided, terminationGracePeriodSeconds will be set to 180
        spec["terminationGracePeriodSeconds"] = self.termination_grace_period

        # Existing DV will be used as the VM's DV; dataVolumeTemplates is not needed
        if self.existing_data_volume:
            del res["spec"]["dataVolumeTemplates"]
            spec = self._update_vm_storage_config(
                spec=spec, name=self.existing_data_volume.name
            )
        # Template's dataVolumeTemplates will be replaced with self.data_volume_template
        elif self.data_volume_template:
            res["spec"]["dataVolumeTemplates"] = [self.data_volume_template]
            spec = self._update_vm_storage_config(
                spec=spec, name=self.data_volume_template["metadata"]["name"]
            )
        # Otherwise clone self.data_volume
        else:
            # dataVolumeTemplates needs to be updated with the source accessModes,
            # volumeMode and storageClass
            # TODO: removed once supported in templates
            dv_pvc_spec = res["spec"]["dataVolumeTemplates"][0]["spec"]["pvc"]
            dv_pvc_spec[
                "storageClassName"
            ] = self.data_volume.pvc.instance.spec.storageClassName
            dv_pvc_spec["accessModes"] = self.data_volume.pvc.instance.spec.accessModes
            dv_pvc_spec["volumeMode"] = self.data_volume.pvc.instance.spec.volumeMode
            # dataVolumeTemplates needs to be updated with the needed storage size,
            # if the size of the golden_image is more than the Template's default storage size.
            if self.cloned_dv_size:
                dv_pvc_spec.setdefault("resources", {}).setdefault("requests", {})[
                    "storage"
                ] = self.cloned_dv_size

        return res

    def _update_vm_storage_config(self, spec, name):
        # volume name and disk name should be updated
        for volume in spec["volumes"]:
            if "dataVolume" in volume:
                volume["name"] = name
                volume["dataVolume"]["name"] = name
        for disk in spec["domain"]["devices"]["disks"]:
            # oc process assigns the VMs name to the boot disk
            if disk["name"] == self.name:
                disk["name"] = name

        return spec

    def _extract_os_from_template(self):
        return re.search(
            r".*/([a-z]+)",
            [label for label in self.template_labels if Template.Labels.OS in label][0],
        ).group(1)

    def process_template(self):
        # Common templates use golden image clone as a default for VM DV
        # SRC_PVC_NAME - to support minor releases, this value needs to be passed. Currently
        # the templates only have one name per major OS.
        # SRC_PVC_NAMESPACE parameters is not passed so the default value will be used.
        # If existing DV or custom dataVolumeTemplates are used, use mock source PVC name and namespace
        template_kwargs = {
            "NAME": self.name,
            "SRC_PVC_NAME": self.data_volume.name if self.data_volume else "mock_pvc",
            "SRC_PVC_NAMESPACE": self.data_volume.namespace
            if self.data_volume
            else "mock_pvc_ns",
        }

        # Set password for non-Windows VMs; for Windows VM, the password is already set in the image
        if OS_FLAVOR_WINDOWS not in self.os_flavor:
            template_kwargs["CLOUD_USER_PASSWORD"] = OS_LOGIN_PARAMS[self.os_flavor][
                "password"
            ]

        template_instance = self.get_template_by_labels()
        resources_list = template_instance.process(
            client=get_admin_client(), **template_kwargs
        )
        for resource in resources_list:
            if (
                resource["kind"] == VirtualMachine.kind
                and resource["metadata"]["name"] == self.name
            ):
                return resource

        raise ValueError(f"Template not found for {self.name}")

    def get_template_by_labels(self):
        template = list(
            Template.get(
                dyn_client=self.client,
                singular_name=Template.singular_name,
                namespace="openshift",
                label_selector=",".join(
                    [f"{label}=true" for label in self.template_labels]
                ),
            ),
        )

        assert (
            len(template) == 1
        ), f"More than one template matches {self.template_labels}"

        return template[0]


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


def run_command(command, verify_stderr=True):
    """
    Run command locally.

    Args:
        command (list): Command to run.
        verify_stderr (bool): Check command stderr.

    Returns:
        tuple: True, out if command succeeded, False, err otherwise.
    """
    p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate()
    out_decoded = out.decode("utf-8")
    err_decoded = err.decode("utf-8")

    if p.returncode != 0:
        LOGGER.error(f"Failed to run {command}. rc: {p.returncode}")
        return False, out_decoded, err_decoded

    # From this point and onwards we are guaranteed that p.returncode == 0
    if err and verify_stderr:
        LOGGER.error(f"Failed to run {command}. error: {err_decoded}")
        return False, out_decoded, err_decoded

    return True, out_decoded, err_decoded


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
        virtctl_cmd += ["-n", namespace]

    if kubeconfig:
        virtctl_cmd += ["--kubeconfig", kubeconfig]

    virtctl_cmd += command
    res, out, err = run_command(command=virtctl_cmd)

    return res, out, err


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


class ServiceForVirtualMachineForTests(Service):
    def __init__(
        self,
        name,
        namespace,
        vm,
        port,
        service_type=Service.Type.CLUSTER_IP,
        target_ip=None,
        ip_family_policy=IP_FAMILY_POLICY_PREFER_DUAL_STACK,
        ip_families=None,
        teardown=True,
        rhel7_workers=False,
    ):
        super().__init__(name=name, namespace=namespace, teardown=teardown)
        self.vm = vm
        self.vmi = vm.vmi
        self.port = port
        self.service_type = service_type
        self.target_ip = target_ip
        self.rhel7_workers = rhel7_workers
        self.ip_family_policy = ip_family_policy
        self.ip_families = ip_families

    def to_dict(self):
        res = super().to_dict()
        res["spec"] = {
            "ports": [{"port": self.port, "protocol": "TCP"}],
            "selector": {"kubevirt.io/domain": self.vm.name},
            "sessionAffinity": "None",
            "type": self.service_type,
        }

        res["spec"]["ipFamilyPolicy"] = self.ip_family_policy
        if self.ip_families:
            res["spec"]["ipFamilies"] = self.ip_families

        return res

    def service_ip(self, ip_family=None):
        if self.rhel7_workers:
            return utilities.network.get_vmi_ip_v4_by_name(
                vm=self.vm, name=[*self.vm.networks][0]
            )

        if self.service_type == Service.Type.CLUSTER_IP:
            if ip_family:
                cluster_ips = [
                    cluster_ip
                    for cluster_ip in self.vm.custom_service.instance.spec.clusterIPs
                    if str(ipaddress.ip_address(cluster_ip).version) in ip_family
                ]
                assert (
                    cluster_ips
                ), f"No {ip_family} addresses in service {self.vm.custom_service.name}"
                return cluster_ips[0]

            return self.instance.spec.clusterIP

        if self.service_type == Service.Type.NODE_PORT:
            if ip_family:
                internal_ips = [
                    internal_ip
                    for internal_ip in self.vmi.node.instance.status.addresses
                    if str(ipaddress.ip_address(internal_ip).version) in ip_family
                ]
                assert (
                    internal_ips
                ), f"No {ip_family} addresses in node {self.vmi.node.name}"
                return internal_ips[0]

            return (
                self.target_ip
                or get_schedulable_nodes_ips(nodes=[self.vmi.node])[self.vmi.node.name]
            )

    @property
    def service_port(self):
        if self.rhel7_workers:
            return self.port

        if self.service_type == Service.Type.CLUSTER_IP:
            return self.instance.attributes.spec.ports[0]["port"]

        if self.service_type == Service.Type.NODE_PORT:
            node_port = camelcase_to_mixedcase(camelcase_str=self.service_type)
            return self.instance.attributes.spec.ports[0][node_port]


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


def wait_for_ssh_connectivity(vm, timeout=120, tcp_timeout=60):
    LOGGER.info(f"Wait for {vm.name} SSH connectivity.")

    sampler = TimeoutSampler(
        wait_timeout=timeout,
        sleep=5,
        func=vm.ssh_exec.executor().is_connective,
        tcp_timeout=tcp_timeout,
    )
    for sample in sampler:
        if sample:
            return


def wait_for_console(vm, console_impl):
    with console_impl(vm=vm, timeout=1500):
        LOGGER.info(f"Successfully connected to {vm.name} console")


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


def validate_windows_guest_agent_info(vm):
    """ Compare guest OS info from VMI (reported by guest agent) and from OS itself. """
    windown_os_info = get_windows_os_info(ssh_exec=vm.ssh_exec)
    for key, val in get_guest_os_info_from_vmi(vmi=vm.vmi).items():
        if key != "id":
            assert val.split("r")[0] if "version" in key else val in windown_os_info


def validate_vmi_ga_info_vs_windows_os_info(vm):
    """ Compare OS data from VMI object vs Windows guest OS data. """
    vmi_info = dict(vm.vmi.instance.status.guestOSInfo)
    os_info = get_windows_os_release(ssh_exec=vm.ssh_exec)

    assert vmi_info, "VMI doesn't have guest agent data!"
    for key, val in vmi_info.items():
        if key != "id":
            assert (
                val.split("r")[0] if "version" in key else val in os_info
            ), f"Data mismatch! VMI data {val} not in OS data {os_info}"


def get_windows_os_release(ssh_exec):
    cmd = shlex.split(
        "wmic os get BuildNumber, Caption, OSArchitecture, Version /value"
    )
    return ssh_exec.run_command(command=cmd)[1]


def get_guest_os_info_from_vmi(vmi):
    """ Gets guest OS info from VMI. """
    guest_os_info_dict = dict(vmi.instance.status.guestOSInfo)
    assert guest_os_info_dict, "Guest agent not installed/active."
    return guest_os_info_dict


def get_windows_os_info(ssh_exec):
    """
    Gets Windows OS info via remote cli tool from systeminfo.
    Return string of OS Name and OS Version output of systeminfo.
    """
    cmd = shlex.split(r'systeminfo | findstr /B /C:"OS Name" /C:"OS Version"')
    return ssh_exec.run_command(command=cmd)[1]


def wait_for_windows_vm(vm, version, timeout=1500):
    """
    Samples Windows VM; wait for it to complete the boot process.
    """

    LOGGER.info(
        f"Windows VM {vm.name} booting up, "
        f"will attempt to access it up to {round(timeout / 60)} minutes."
    )

    sampler = TimeoutSampler(
        wait_timeout=timeout,
        sleep=15,
        func=vm.ssh_exec.run_command,
        command=shlex.split("wmic os get Caption /value"),
    )
    for sample in sampler:
        if version in str(sample):
            return True


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


@contextmanager
def import_vm(
    name,
    namespace,
    provider_credentials_secret_name,
    provider_credentials_secret_namespace,
    provider_type,
    target_vm_name,
    resource_mapping_name=None,
    resource_mapping_namespace=None,
    vm_id=None,
    vm_name=None,
    cluster_name=None,
    provider_mappings=None,
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
        provider_mappings=provider_mappings,
        provider_type=provider_type,
        vm_name=vm_name,
        cluster_name=cluster_name,
        resource_mapping_name=resource_mapping_name,
        resource_mapping_namespace=resource_mapping_namespace,
    ) as vmimport:
        yield vmimport


# TODO: Remove once bug 1945703 is fixed
def get_guest_os_info(vmi):
    sampler = TimeoutSampler(
        wait_timeout=360,
        sleep=5,
        func=lambda: vmi.instance.status.guestOSInfo,
    )

    try:
        for sample in sampler:
            if sample.get("id"):
                return dict(sample)
    except TimeoutExpiredError:
        LOGGER.error("VMI doesn't have guest agent data")
        raise


def get_windows_os_dict(windows_version):
    windows_os_dict = [
        os_dict
        for win_os in py_config["system_windows_os_matrix"]
        for os_name, os_dict in win_os.items()
        if os_name == windows_version
    ]
    if windows_os_dict:
        return windows_os_dict[0]
    raise KeyError(f"Failed to extract {windows_version} from system_windows_os_matrix")


def get_rhel_os_dict(rhel_version):
    rhel_os_dict = [
        os_dict
        for rhel_os in py_config["system_rhel_os_matrix"]
        for os_name, os_dict in rhel_os.items()
        if os_name == rhel_version
    ]
    if rhel_os_dict:
        return rhel_os_dict[0]
    raise KeyError(f"Failed to extract {rhel_version} from system_rhel_os_matrix")


def running_vm(vm, wait_for_interfaces=True, enable_ssh=True):
    """
    Wait for the VMI to be in Running state.

    Args:
        vm (VirtualMachine): VM object.
        wait_for_interfaces (bool): Is waiting for VM's interfaces mandatory for declaring VM as running.
        enable_ssh (bool): Enable SSh service in the VM.

    Returns:
        VirtualMachine: VM object.
    """
    # For VMs from common templates
    start_vm_timeout = TIMEOUT_4MIN

    # For VMs from common templates (Linux and Windows based)
    if vm.is_vm_from_template:
        # Windows 10 takes longer to start
        start_vm_timeout = (
            2600 if "windows10" in vm.labels["vm.kubevirt.io/template"] else 2100
        )

    if not vm.instance.spec.running:
        vm.start(wait=True, timeout=start_vm_timeout)

    # Verify the VM was started (either in this function or before calling it).
    vm.vmi.wait_until_running()

    if wait_for_interfaces:
        wait_for_vm_interfaces(vmi=vm.vmi)

    if enable_ssh:
        wait_for_ssh_connectivity(vm=vm)

    return vm


def migrate_and_verify(
    vm, timeout=720, wait_for_interfaces=True, check_ssh_connectivity=False
):
    node_before = vm.vmi.node
    LOGGER.info(f"VMI is running on {node_before.name} before migration.")
    with VirtualMachineInstanceMigration(
        name=vm.name, namespace=vm.namespace, vmi=vm.vmi
    ) as mig:
        mig.wait_for_status(status=mig.Status.SUCCEEDED, timeout=timeout)

    assert vm.vmi.node != node_before

    assert vm.vmi.instance.status.migrationState.completed
    if wait_for_interfaces:
        wait_for_vm_interfaces(vmi=vm.vmi)
    if check_ssh_connectivity:
        wait_for_ssh_connectivity(vm=vm)


# TODO : remove restart_guest_agent and replace all calls to it with wait_for_vm_interfaces once BZ 1907707 is fixed
def restart_guest_agent(vm):
    bug_num = 1907707
    restart = "restart qemu-guest-agent"
    if (
        get_bug_status(
            bugzilla_connection_params=get_bugzilla_connection_params(), bug=bug_num
        )
        not in BUG_STATUS_CLOSED
    ):
        LOGGER.info(f"{restart} (Workaround for bug {bug_num}).")
        run_ssh_commands(
            host=vm.ssh_exec, commands=[shlex.split(f"sudo systemctl {restart}")]
        )
        running_vm(vm=vm, enable_ssh=False)
    else:
        LOGGER.warning(
            f"bug {bug_num} is resolved. please remove all references to it from the automation"
        )


def vm_cloud_init_volume(vm_spec):
    cloud_init_volume = [
        vol
        for vol in vm_spec.setdefault("volumes", [])
        if vol["name"] == CLOUD_INIT_DISK_NAME
    ]

    if cloud_init_volume:
        return cloud_init_volume[0]

    # If cloud init volume needs to be added
    vm_spec["volumes"].append({"name": CLOUD_INIT_DISK_NAME})
    return vm_spec["volumes"][-1]
