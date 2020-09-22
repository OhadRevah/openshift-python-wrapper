import logging
import socket
import ssl
import urllib.error
import urllib.request
from contextlib import contextmanager

from pytest_testconfig import config as py_config
from resources.datavolume import DataVolume
from resources.deployment import Deployment


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
    if os_matrix:
        os_matrix_key = [*os_matrix][0]
        image = os_matrix[os_matrix_key]["image_path"]
        dv_name = os_matrix_key
    else:
        image = params_dict.get("image", "")
        dv_name = params_dict.get("dv_name").replace(".", "-").lower()
    dv_kwargs = {
        "dv_name": dv_name,
        "namespace": namespace.name,
        "source": source,
        "size": params_dict.get("dv_size", "38Gi" if "win" in image else "25Gi"),
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
        if storage_class == "hostpath-provisioner"
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
                dv.wait(timeout=2400 if "win" in image else 1200)
        yield dv


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
