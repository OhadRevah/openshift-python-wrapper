# -*- coding: utf-8 -*-

import logging
import shlex
from contextlib import contextmanager

import requests
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.configmap import ConfigMap
from ocp_resources.datavolume import DataVolume
from ocp_resources.pod import Pod
from ocp_resources.role_binding import RoleBinding
from ocp_resources.route import Route
from ocp_resources.service import Service
from ocp_resources.storage_class import StorageClass
from ocp_resources.upload_token_request import UploadTokenRequest
from ocp_resources.utils import TimeoutSampler
from ocp_resources.volume_snapshot import VolumeSnapshotClass
from openshift.dynamic.exceptions import ResourceNotFoundError
from pytest_testconfig import config as py_config

from tests.conftest import vm_instance_from_template
from utilities.constants import OS_FLAVOR_CIRROS
from utilities.infra import Images, get_cert, run_ssh_commands
from utilities.storage import create_dv
from utilities.virt import (
    VirtualMachineForTests,
    running_vm,
    validate_vmi_ga_info_vs_windows_os_info,
    wait_for_windows_vm,
)


LOGGER = logging.getLogger(__name__)


@contextmanager
def import_image_to_dv(
    dv_name, images_https_server_name, volume_mode, storage_ns_name, access_mode
):
    url = get_file_url_https_server(
        images_https_server=images_https_server_name, file_name=Images.Cirros.QCOW2_IMG
    )
    with ConfigMap(
        name="https-cert-configmap",
        namespace=storage_ns_name,
        data={"tlsregistry.crt": get_cert(server_type="https_cert")},
    ) as configmap:
        with create_dv(
            source="http",
            dv_name=dv_name,
            namespace=configmap.namespace,
            url=url,
            cert_configmap=configmap.name,
            volume_mode=volume_mode,
            storage_class=py_config["default_storage_class"],
            access_modes=access_mode,
        ) as dv:
            yield dv


@contextmanager
def upload_image_to_dv(
    dv_name, volume_mode, storage_ns_name, storage_class, client, consume_wffc=True
):
    with create_dv(
        source="upload",
        dv_name=dv_name,
        namespace=storage_ns_name,
        size="3Gi",
        storage_class=storage_class,
        volume_mode=volume_mode,
        client=client,
        consume_wffc=consume_wffc,
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=120)
        yield dv


@contextmanager
def upload_token_request(storage_ns_name, pvc_name, data):
    with UploadTokenRequest(
        name="upload-image", namespace=storage_ns_name, pvc_name=pvc_name
    ) as utr:
        token = utr.create().status.token
        LOGGER.info("Ensure upload was successful")
        sampler = TimeoutSampler(
            wait_timeout=120, sleep=5, func=upload_image, token=token, data=data
        )
        for sample in sampler:
            if sample == 200:
                break


def check_disk_count_in_vm(vm):
    LOGGER.info("Check disk count.")
    cmd = shlex.split("lsblk | grep disk | wc -l")
    out = run_ssh_commands(host=vm.ssh_exec, commands=cmd)[0].strip()
    assert out == str(
        len(vm.instance.spec.template.spec.domain.devices.disks)
    ), "Failed to verify actual disk count against VMI"


@contextmanager
def create_vm_from_dv(
    dv,
    vm_name="cirros-vm",
    image=None,
    start=True,
    os_flavor=OS_FLAVOR_CIRROS,
    node_selector=None,
    memory_requests=Images.Cirros.DEFAULT_MEMORY_SIZE,
):
    with VirtualMachineForTests(
        name=vm_name,
        namespace=dv.namespace,
        data_volume=dv,
        image=image,
        node_selector=node_selector,
        memory_requests=memory_requests,
        os_flavor=os_flavor,
    ) as vm:
        if start:
            running_vm(vm=vm, wait_for_interfaces=False)
        yield vm


def create_windows_vm_validate_guest_agent_info(
    cloud_init_data,
    dv,
    namespace,
    network_configuration,
    unprivileged_client,
    vm_params,
):
    with vm_instance_from_template(
        request=vm_params,
        cloud_init_data=cloud_init_data,
        data_volume=dv,
        network_configuration=network_configuration,
        namespace=namespace,
        unprivileged_client=unprivileged_client,
    ) as vm_dv:
        wait_for_windows_vm(vm=vm_dv, version=vm_params["os_version"], timeout=1800)
        validate_vmi_ga_info_vs_windows_os_info(vm=vm_dv)


def upload_image(token, data, asynchronous=False):
    headers = {"Authorization": f"Bearer {token}"}
    uploadproxy = Route(name="cdi-uploadproxy", namespace=py_config["hco_namespace"])
    uploadproxy_url = f"https://{uploadproxy.host}/v1alpha1/upload"
    if asynchronous:
        uploadproxy_url = f"{uploadproxy_url}-async"
    LOGGER.info(msg=f"Upload {data} to {uploadproxy_url}")
    try:
        with open(data, "rb") as fd:
            fd_data = fd.read()
    except (OSError, IOError):
        fd_data = data

    return requests.post(
        url=uploadproxy_url, data=fd_data, headers=headers, verify=False
    ).status_code


class HttpService(Service):
    def to_dict(self):
        res = super()._base_body()
        res.update(
            {
                "spec": {
                    "selector": {"name": "internal-http"},
                    "ports": [
                        {"name": "rate-limit", "port": 82},
                        {"name": "http-auth", "port": 81},
                        {"name": "http-no-auth", "port": 80},
                        {"name": "https", "port": 443},
                    ],
                }
            }
        )
        return res


def get_file_url_https_server(images_https_server, file_name):
    return f"{images_https_server}{Images.Cirros.DIR}/{file_name}"


@contextmanager
def create_cluster_role(name, api_groups, verbs, permissions_to_resources):
    """
    Create cluster role
    """
    with ClusterRole(
        name=name,
        api_groups=api_groups,
        permissions_to_resources=permissions_to_resources,
        verbs=verbs,
    ) as cluster_role:
        yield cluster_role


@contextmanager
def create_role_binding(
    name,
    namespace,
    subjects_kind,
    subjects_name,
    role_ref_kind,
    role_ref_name,
    subjects_namespace=None,
    subjects_api_group=None,
):
    """
    Create role binding
    """
    with RoleBinding(
        name=name,
        namespace=namespace,
        subjects_kind=subjects_kind,
        subjects_name=subjects_name,
        subjects_api_group=subjects_api_group,
        subjects_namespace=subjects_namespace,
        role_ref_kind=role_ref_kind,
        role_ref_name=role_ref_name,
    ) as role_binding:
        yield role_binding


@contextmanager
def set_permissions(
    role_name,
    verbs,
    permissions_to_resources,
    binding_name,
    namespace,
    subjects_kind,
    subjects_name,
    subjects_api_group=None,
    subjects_namespace=None,
):
    with create_cluster_role(
        name=role_name,
        api_groups=["cdi.kubevirt.io"],
        permissions_to_resources=permissions_to_resources,
        verbs=verbs,
    ) as cluster_role:
        with create_role_binding(
            name=binding_name,
            namespace=namespace,
            subjects_kind=subjects_kind,
            subjects_name=subjects_name,
            subjects_api_group=subjects_api_group,
            subjects_namespace=subjects_namespace,
            role_ref_kind=cluster_role.kind,
            role_ref_name=cluster_role.name,
        ) as role_binding:
            yield [cluster_role, role_binding]


def create_vm_and_verify_image_permission(dv):
    with create_vm_from_dv(dv=dv) as vm:
        vm.vmi.wait_until_running()
        v_pod = vm.vmi.virt_launcher_pod
        LOGGER.debug("Check image exist, permission and ownership")
        output = v_pod.execute(
            command=["ls", "-l", "/var/run/kubevirt-private/vmi-disks/dv-disk"]
        )
        assert "disk.img" in output
        assert "-rw-rw----." in output
        assert "qemu qemu" in output


def storage_params(storage_class_matrix):
    storage_class = [*storage_class_matrix][0]
    return {
        "storage_class": storage_class,
        "volume_mode": storage_class_matrix[storage_class]["volume_mode"],
        "access_modes": storage_class_matrix[storage_class]["access_mode"],
    }


def get_importer_pod(
    dyn_client,
    namespace,
):
    pods = list(Pod.get(dyn_client=dyn_client, namespace=namespace))
    for pod in pods:
        if pod.name.startswith("importer"):
            return pod
    raise ResourceNotFoundError


def smart_clone_supported_by_sc(sc, client):
    sc_instance = StorageClass(name=sc).instance
    for vsc in VolumeSnapshotClass.get(dyn_client=client):
        if vsc.instance.get("driver") == sc_instance.get("provisioner"):
            return True
    return False
