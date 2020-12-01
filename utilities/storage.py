import logging
import os
import socket
import ssl
import urllib.error
import urllib.request
from contextlib import contextmanager

import requests
from pytest_testconfig import config as py_config
from resources.datavolume import DataVolume
from resources.deployment import Deployment
from resources.persistent_volume_claim import PersistentVolumeClaim
from resources.pod import Pod
from resources.storage_class import StorageClass

from utilities.infra import url_excluded_from_validation, validate_file_exists_in_url
from utilities.virt import run_virtctl_command


LOGGER = logging.getLogger(__name__)


@contextmanager
def create_dv(
    dv_name,
    namespace,
    storage_class,
    volume_mode,
    url=None,
    source="http",
    content_type=DataVolume.ContentType.KUBEVIRT,
    size="5Gi",
    secret=None,
    cert_configmap=None,
    hostpath_node=None,
    access_modes=DataVolume.AccessMode.RWO,
    client=None,
    source_pvc=None,
    source_namespace=None,
    teardown=True,
):
    if source in ("http", "https"):
        if not url_excluded_from_validation(url):
            # Make sure URL and the file exists
            validate_file_exists_in_url(url=url)

    with DataVolume(
        source=source,
        name=dv_name,
        namespace=namespace,
        url=url,
        content_type=content_type,
        size=size,
        storage_class=storage_class,
        cert_configmap=cert_configmap,
        volume_mode=volume_mode,
        hostpath_node=hostpath_node,
        access_modes=access_modes,
        secret=secret,
        client=client,
        source_pvc=source_pvc,
        source_namespace=source_namespace,
        teardown=teardown,
    ) as dv:
        yield dv


def data_volume(
    namespace,
    storage_class_matrix=None,
    storage_class=None,
    schedulable_nodes=None,
    request=None,
    os_matrix=None,
):
    """
    DV creation using create_dv.
    """
    if not storage_class_matrix:
        storage_class_matrix = get_storage_class_dict_from_matrix(
            storage_class=storage_class
        )

    storage_class = [*storage_class_matrix][0]
    # Save with a different name to avoid confusing.
    storage_class_dict = storage_class_matrix

    params_dict = request.param if request else {}

    # Set DV attributes
    # DV name is the only mandatory value
    # Values can be extracted from request.param or from
    # rhel_os_matrix or windows_os_matrix (passed as os_matrix)
    source = params_dict.get("source", "http")

    # DV namespace may not be in the same namespace as the originating test
    # If a namespace is passes in request.param, use it instead of the test's namespace
    dv_namespace = params_dict.get("dv_namespace", namespace.name)

    if os_matrix:
        os_matrix_key = [*os_matrix][0]
        image = os_matrix[os_matrix_key]["image_path"]
        dv_name = os_matrix_key
        dv_size = os_matrix[os_matrix_key].get("dv_size")
    else:
        image = params_dict.get("image", "")
        dv_name = params_dict.get("dv_name").replace(".", "-").lower()
        dv_size = params_dict.get("dv_size")
    dv_kwargs = {
        "dv_name": dv_name,
        "namespace": dv_namespace,
        "source": source,
        "size": dv_size,
        "storage_class": params_dict.get("storage_class", storage_class),
        "access_modes": params_dict.get(
            "access_modes", storage_class_dict[storage_class]["access_mode"]
        ),
        "volume_mode": params_dict.get(
            "volume_mode",
            storage_class_dict[storage_class]["volume_mode"],
        ),
        "content_type": DataVolume.ContentType.KUBEVIRT,
        # In hpp, volume must reside on the same worker as the VM
        "hostpath_node": schedulable_nodes[0].name
        if sc_is_hpp_with_immediate_volume_binding(sc=storage_class)
        else None,
    }
    if source == "http":
        dv_kwargs["url"] = f"{get_images_external_http_server()}{image}"
    elif source == "https":
        dv_kwargs["url"] = f"{get_images_https_server()}{image}"
    if params_dict.get("cert_configmap"):
        dv_kwargs["cert_configmap"] = params_dict.get("cert_configmap")
    # Create dv
    with create_dv(**{k: v for k, v in dv_kwargs.items() if v is not None}) as dv:
        if params_dict.get("wait", True):
            if source == "upload":
                dv.wait_for_condition(
                    condition=DataVolume.Condition.Type.BOUND,
                    status=DataVolume.Condition.Status.TRUE,
                    timeout=300,
                )
                dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=180)
            else:
                dv.wait(timeout=3000 if "win" in image else 1600)
        yield dv


def downloaded_image(remote_name, local_name):
    """
    Download image to local tmpdir path
    """
    url = f"{get_images_external_http_server()}{remote_name}"
    assert requests.head(url).status_code == requests.codes.ok
    LOGGER.info(f"Download {url} to {local_name}")
    urllib.request.urlretrieve(url, local_name)
    try:
        assert os.path.isfile(local_name)
    except FileNotFoundError as err:
        LOGGER.error(err)
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


def get_storage_class_dict_from_matrix(storage_class):
    storages = py_config["system_storage_class_matrix"]
    matching_storage_classes = [sc for sc in storages if [*sc][0] == storage_class]
    if not matching_storage_classes:
        raise ValueError(f"{storage_class} not found in {storages}")
    return matching_storage_classes[0]


def sc_is_hpp_with_immediate_volume_binding(sc):
    return (
        sc == "hostpath-provisioner"
        and StorageClass(name=sc).instance["volumeBindingMode"]
        == StorageClass.VolumeBindingMode.Immediate
    )


def sc_volume_binding_mode_is_wffc(sc):
    return (
        StorageClass(name=sc).instance["volumeBindingMode"]
        == StorageClass.VolumeBindingMode.WaitForFirstConsumer
    )


@contextmanager
def virtctl_upload_dv(
    namespace,
    name,
    image_path,
    size,
    pvc=False,
    storage_class=None,
    volume_mode=None,
    access_mode=None,
    uploadproxy_url=None,
    wait_secs=None,
    insecure=False,
    no_create=False,
):
    command = [
        "image-upload",
        f"{'dv' if not pvc else pvc}",
        f"{name}",
        f"--image-path={image_path}",
        f"--size={size}",
    ]
    if pvc:
        command[1] = "pvc"
    if storage_class:
        if not (
            volume_mode and access_mode
        ):  # In case either one of them is missing, must fetch missing mode/s from matrix
            storage_class_dict = get_storage_class_dict_from_matrix(
                storage_class=storage_class
            )
            storage_class = [*storage_class_dict][0]
        # There is still an option that one mode was passed by caller, will use the passed value
        volume_mode = volume_mode or storage_class_dict[storage_class]["volume_mode"]
        access_mode = access_mode or storage_class_dict[storage_class]["access_mode"]
        command.append(f"--storage-class={storage_class}")
    if access_mode:
        command.append(f"--access-mode={access_mode}")
    if uploadproxy_url:
        command.append(f"--uploadproxy-url={uploadproxy_url}")
    if wait_secs:
        command.append(f"--wait-secs={wait_secs}")
    if insecure:
        command.append("--insecure")
    if volume_mode == "Block":
        command.append("--block-volume")
    if no_create:
        command.append("--no-create")

    yield run_virtctl_command(command=command, namespace=namespace)
    if pvc:
        PersistentVolumeClaim(namespace=namespace, name=name).delete(wait=True)
    else:
        DataVolume(namespace=namespace, name=name).delete(wait=True)


class HttpDeployment(Deployment):
    def to_dict(self):
        res = super()._base_body()
        res.update(
            {
                "spec": {
                    "replicas": 1,
                    "selector": {"matchLabels": {"name": "internal-http"}},
                    "template": {
                        "metadata": {
                            "labels": {
                                "name": "internal-http",
                                "cdi.kubevirt.io/testing": "",
                            }
                        },
                        "spec": {
                            "terminationGracePeriodSeconds": 0,
                            "containers": [
                                {
                                    "name": "http",
                                    "image": "quay.io/openshift-cnv/qe-cnv-tests-internal-http",
                                    "imagePullPolicy": "Always",
                                    "command": ["/usr/sbin/nginx"],
                                    "readinessProbe": {
                                        "httpGet": {"path": "/", "port": 80},
                                        "initialDelaySeconds": 20,
                                        "periodSeconds": 20,
                                    },
                                    "securityContext": {"privileged": True},
                                    "livenessProbe": {
                                        "httpGet": {"path": "/", "port": 80},
                                        "initialDelaySeconds": 20,
                                        "periodSeconds": 20,
                                    },
                                }
                            ],
                        },
                    },
                }
            }
        )
        return res


class ErrorMsg:
    """
    error messages that might show in pod containers
    """

    EXIT_STATUS_2 = "Unable to process data: exit status 2"
    CERTIFICATE_SIGNED_UNKNOWN_AUTHORITY = "certificate signed by unknown authority"
    DISK_IMAGE_IN_CONTAINER_NOT_FOUND = (
        "Unable to process data: Failed to find VM disk image file in the container "
        "image"
    )
    LARGER_PVC_REQUIRED = "A larger PVC is required"
    INVALID_FORMAT_FOR_QCOW = "Unable to process data: Invalid format qcow for image "
    COULD_NOT_OPEN_SIZE_TOO_BIG = "Unable to process data: qemu-img: Could not open '/data/disk.img': L1 size too big"
    REQUESTED_RANGE_NOT_SATISFIABLE = (
        "Unable to process data: qemu-img: curl: The requested URL returned error: "
        "416 Requested Range Not Satisfiable"
    )
    CANNOT_CREATE_RESOURCE = r".*cannot create resource.*|.*has insufficient permissions in clone source namespace.*"
    CANNOT_DELETE_RESOURCE = r".*cannot delete resource.*|.*has insufficient permissions in clone source namespace.*"


class PodWithPVC(Pod):
    def __init__(self, name, namespace, pvc_name, volume_mode, teardown=True):
        super().__init__(name=name, namespace=namespace, teardown=teardown)
        self._pvc_name = pvc_name
        self._volume_mode = volume_mode

    def to_dict(self):
        res = super().to_dict()

        if self._volume_mode == DataVolume.VolumeMode.BLOCK:
            volume_path = {
                "volumeDevices": [
                    {"devicePath": "/pvc/disk.img", "name": self._pvc_name}
                ]
            }
        else:
            volume_path = {
                "volumeMounts": [{"mountPath": "/pvc", "name": self._pvc_name}]
            }

        res.update(
            {
                "spec": {
                    "containers": [
                        {
                            "name": "runner",
                            "image": "quay.io/openshift-cnv/qe-cnv-tests-net-util-container",
                            "command": [
                                "/bin/bash",
                                "-c",
                                "echo ok > /tmp/healthy && sleep INF",
                            ],
                            **volume_path,
                        }
                    ],
                    "volumes": [
                        {
                            "name": self._pvc_name,
                            "persistentVolumeClaim": {"claimName": self._pvc_name},
                        }
                    ],
                }
            }
        )
        return res


def data_volume_template_dict(
    target_dv_name,
    target_dv_namespace,
    source_dv,
    worker_node=None,
):
    # worker node used and mandatory only in case of hpp SC
    source_dv_pvc = source_dv.instance.spec.pvc
    data_volume_template_dict = DataVolume(
        name=target_dv_name,
        namespace=target_dv_namespace,
        source="pvc",
        storage_class=source_dv_pvc.storageClassName,
        volume_mode=source_dv_pvc.volumeMode,
        access_modes=",".join(source_dv_pvc.accessModes),
        size=source_dv_pvc.resources.requests.storage,
        source_pvc=source_dv.name,
        source_namespace=source_dv.namespace,
    ).to_dict()

    if DataVolume.AccessMode.RWO in source_dv_pvc.accessModes:
        data_volume_template_dict["metadata"].setdefault("annotations", {})[
            "kubevirt.io/provisionOnNode"
        ] = worker_node.name

    return data_volume_template_dict
