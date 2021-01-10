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
import rrmngmnt
import yaml
from pytest_testconfig import config as py_config
from resources.datavolume import DataVolume
from resources.route import Route
from resources.secret import Secret
from resources.service import Service
from resources.service_account import ServiceAccount
from resources.sriov_network import SriovNetwork
from resources.template import Template
from resources.utils import TimeoutExpiredError, TimeoutSampler
from resources.virtual_machine import VirtualMachine
from resources.virtual_machine_import import VirtualMachineImport

import utilities.network
from utilities import console
from utilities.infra import (
    BUG_STATUS_CLOSED,
    ClusterHosts,
    camelcase_to_mixedcase,
    get_admin_client,
    get_bug_status,
    get_bugzilla_connection_params,
    get_schedulable_nodes_ips,
)


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
        if (
            get_bug_status(
                bugzilla_connection_params=get_bugzilla_connection_params(), bug=1886453
            )
            not in BUG_STATUS_CLOSED
        ):
            LOGGER.error(
                "Due to bug 1886453 guest agent may not report its status and VM interfaces may not be available."
            )
        else:
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
        generated_data = yaml.dump(_data, width=1000)
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
        cpu_model=None,
        memory_requests=None,
        memory_limits=None,
        memory_guest=None,
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
        running=False,
        run_strategy=None,
        disk_io_options=None,
        rhel7_workers=False,
        username=None,
        password=None,
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
        self.cpu_model = cpu_model
        self.memory_requests = memory_requests
        self.memory_limits = memory_limits
        self.memory_guest = memory_guest
        self.label = label
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

        self.is_vm_from_template = (
            "vm.kubevirt.io/template" in res["metadata"].setdefault("labels", {}).keys()
        )

        # runStrategy and running are mutually exclusive
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

        res, spec = self.update_vm_storage_configuration(res=res, spec=spec)

        if self.cloud_init_data:
            spec = self.update_vm_cloud_init_data(spec=spec)

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

        if self.disk_io_options:
            disks_spec = (
                spec.setdefault("domain", {})
                .setdefault("devices", {})
                .setdefault("disks", [])
            )
            for disk in disks_spec:
                if disk["name"] == "rootdisk":
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
        iface_mac_number = random.randint(0, 255)
        for iface_name in self.interfaces:
            try:
                # On cluster without SR-IOV deploy we will get NotImplementedError
                sriov_network_exists = SriovNetwork(
                    name=iface_name,
                    network_namespace=self.namespace,
                    namespace=py_config["sriov_namespace"],
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

        return spec

    def update_vm_cloud_init_data(self, spec):
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
        # To use the service: ssh_service.service_ip and ssh_service.service_port
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
        service_type=Service.Type.CLUSTER_IP,
        service_ip=None,
        ip_family=None,
    ):
        """
        service_type is set with K8S default service type (ClusterIP)
        service_ip - relevant for node port; default will be set to vm node IP
        ip_family - IP family (IPv4/6)
        To use the service: custom_service.service_ip and custom_service.service_port
        """
        self.custom_service = ServiceForVirtualMachineForTests(
            name=f"{service_name}-{self.name}"[:63],
            namespace=self.namespace,
            vm=self,
            port=port,
            service_type=service_type,
            target_ip=service_ip,
            ip_family=ip_family,
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
        host = rrmngmnt.Host(ip=str(self.ssh_service.service_ip))
        host_user = rrmngmnt.user.User(name=self.username, password=self.password)
        host._set_executor_user(user=host_user)
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
        ssh=False,
        vm_dict=None,
        cpu_cores=None,
        cpu_threads=None,
        cpu_model=None,
        memory_requests=None,
        network_model=None,
        network_multiqueue=None,
        cloud_init_data=None,
        node_selector=None,
        attached_secret=None,
        termination_grace_period=False,
        diskless_vm=False,
        run_strategy=None,
        disk_options_vm=None,
        smm_enabled=None,
        efi_params=None,
        username=None,
        password=None,
        rhel7_workers=False,
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
            username=username,
            password=password,
            rhel7_workers=rhel7_workers,
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

    def process_template(self):
        def _extract_os_from_template():
            return re.search(
                r".*/([a-z]+)",
                [
                    label
                    for label in self.template_labels
                    if Template.Labels.OS in label
                ][0],
            ).group(1)

        def _get_os_password(os_name):
            os_password_dict = {
                "rhel": console.RHEL.PASSWORD,
                "fedora": console.Fedora.PASSWORD,
                "centos": console.Centos.PASSWORD,
            }
            return os_password_dict[os_name]

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

        # Add password to VM for Non-Windows VMs
        if not self.cloud_init_data or not self.cloud_init_data.setdefault(
            "userData", {}
        ).get("password"):
            # Extract OS from template labels
            template_os = _extract_os_from_template()
            if "win" not in template_os:
                template_kwargs["CLOUD_USER_PASSWORD"] = _get_os_password(
                    os_name=template_os
                )

        template_instance = self.get_template_by_labels()
        resources_list = template_instance.process(
            client=get_admin_client(), **template_kwargs
        )
        for resource in resources_list:
            if (
                resource["kind"] == VirtualMachine.kind
                and resource["metadata"]["name"] == self.name
            ):
                spec = resource["spec"]["template"]["spec"]
                # Template have bridge pod network that wont work for migration.
                # Replacing the bridge pod network with masquerade.
                # https://bugzilla.redhat.com/show_bug.cgi?id=1751869
                interfaces_dict = spec["domain"]["devices"]["interfaces"][0]
                if "bridge" in interfaces_dict:
                    interfaces_dict["masquerade"] = interfaces_dict.pop("bridge")

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

        # TODO: remove - workaround on cluster with multiple templates xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
        return [t for t in template if not re.search(r"\d+$", t.name)][0]

        # assert (
        #     len(template) == 1
        # ), f"More than one template matches {self.template_labels}"
        #
        # return template[0]


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

    if p.returncode != 0:
        LOGGER.error(f"Failed to run {command}. rc: {p.returncode}")
        return False, out.decode("utf-8")

    if err and verify_stderr:
        LOGGER.error(f"Failed to run {command}. error: {err}")
        return False, err

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
        virtctl_cmd += ["-n", namespace]

    if kubeconfig:
        virtctl_cmd += ["--kubeconfig", kubeconfig]

    virtctl_cmd += command
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


class ServiceForVirtualMachineForTests(Service):
    def __init__(
        self,
        name,
        namespace,
        vm,
        port,
        service_type=Service.Type.CLUSTER_IP,
        target_ip=None,
        ip_family=None,
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
        self.ip_family = ip_family

    def to_dict(self):
        res = super().to_dict()
        res["spec"] = {
            "ports": [{"port": self.port, "protocol": "TCP"}],
            "selector": {"kubevirt.io/domain": self.vm.name},
            "sessionAffinity": "None",
            "type": self.service_type,
            "ipFamily": self.ip_family or "IPv4",
        }
        return res

    @property
    def service_ip(self):
        if self.rhel7_workers:
            return utilities.network.get_vmi_ip_v4_by_name(
                vmi=self.vmi, name=[*self.vm.networks][0]
            )

        if self.service_type == Service.Type.CLUSTER_IP:
            return self.instance.spec.clusterIP

        if self.service_type == Service.Type.NODE_PORT:
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
        timeout=timeout,
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


# TODO: Remove once bug 1886453 is fixed
def get_guest_os_info(vmi):
    sampler = TimeoutSampler(
        timeout=360,
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
    else:
        raise KeyError(
            f"Failed to extract {windows_version} from system_windows_os_matrix"
        )
