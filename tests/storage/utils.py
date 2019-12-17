# -*- coding: utf-8 -*-

import logging
import os
import urllib.request
from contextlib import contextmanager

import requests
from pytest_testconfig import config as py_config
from resources.configmap import ConfigMap
from resources.datavolume import DataVolume
from resources.pod import Pod
from resources.route import Route
from resources.service import Service
from resources.upload_token_request import UploadTokenRequest
from resources.utils import TimeoutSampler
from utilities import console
from utilities.infra import Images, get_cert, get_images_external_http_server
from utilities.storage import create_dv
from utilities.virt import VirtualMachineForTests, run_virtctl_command


CDI_IMAGES_DIR = "cdi-test-images"
CIRROS_IMAGES_DIR = "cirros_images"

LOGGER = logging.getLogger(__name__)


@contextmanager
def import_image_to_dv(images_https_server_name, volume_mode, storage_ns_name):
    url = get_file_url_https_server(images_https_server_name, Images.Cirros.QCOW2_IMG)
    with ConfigMap(
        name="https-cert-configmap",
        namespace=storage_ns_name,
        data=get_cert("https_cert"),
    ) as configmap:
        with create_dv(
            source="http",
            dv_name="import-image",
            namespace=configmap.namespace,
            url=url,
            cert_configmap=configmap.name,
            volume_mode=volume_mode,
            storage_class=py_config["default_storage_class"],
        ) as dv:
            yield dv


@contextmanager
def upload_image_to_dv(tmpdir, volume_mode, storage_ns_name):
    local_name = f"{tmpdir}/{Images.Cirros.QCOW2_IMG}"
    remote_name = f"{CDI_IMAGES_DIR}/{CIRROS_IMAGES_DIR}/{Images.Cirros.QCOW2_IMG}"
    downloaded_image(remote_name=remote_name, local_name=local_name)
    with create_dv(
        source="upload",
        dv_name="upload-image",
        namespace=storage_ns_name,
        size="3Gi",
        volume_mode=volume_mode,
        storage_class=py_config["default_storage_class"],
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=180)
        with UploadTokenRequest(name="upload-image", namespace=storage_ns_name) as utr:
            token = utr.create().status.token
            LOGGER.info("Ensure upload was successful")
            sampler = TimeoutSampler(
                timeout=120, sleep=5, func=upload_image, token=token, data=local_name,
            )
            for sample in sampler:
                if sample == 200:
                    break
            yield dv


class PodWithPVC(Pod):
    def __init__(self, name, namespace, pvc_name, volume_mode):
        super().__init__(name=name, namespace=namespace)
        self._pvc_name = pvc_name
        self._volume_mode = volume_mode

    def _to_dict(self):
        res = super()._to_dict()

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
                            "image": "quay.io/redhat/cnv-tests-net-util-container",
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


def check_disk_count_in_vm(vm):
    with console.Cirros(vm=vm) as vm_console:
        LOGGER.info(f"Check disk count.")
        vm_console.sendline("lsblk | grep disk | wc -l")
        vm_console.expect(
            str(len(vm.instance.spec.template.spec.domain.devices.disks)), timeout=60
        )


@contextmanager
def create_vm_from_dv(dv, vm_name="cirros-vm", image=None, start=True):
    with VirtualMachineForTests(
        name=vm_name, namespace=dv.namespace, dv=dv.name, image=image
    ) as vm:
        if start:
            vm.start(wait=True)
            vm.vmi.wait_until_running(timeout=300)
        yield vm


def virtctl_upload(namespace, pvc_name, pvc_size, image_path):
    return run_virtctl_command(
        command=[
            "image-upload",
            f"--image-path={image_path}",
            f"--pvc-size={pvc_size}",
            f"--pvc-name={pvc_name}",
            "--insecure",
        ],
        namespace=namespace,
    )


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


def upload_image(token, data):
    headers = {"Authorization": f"Bearer {token}"}
    uploadproxy = Route(name="cdi-uploadproxy", namespace="openshift-cnv")
    uploadproxy_url = f"https://{uploadproxy.host}/v1alpha1/upload"
    LOGGER.info(msg=f"Upload {data} to {uploadproxy_url}")
    with open(data, "rb") as fd:
        fd_data = fd.read()
    return requests.post(
        uploadproxy_url, data=fd_data, headers=headers, verify=False
    ).status_code


def get_images_private_registry_server():
    """
    Fetch url from config and return if available.
    """
    return py_config[py_config["region"]]["registry_server"]


class HttpService(Service):
    def _to_dict(self):
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
    return f"{images_https_server}{CDI_IMAGES_DIR}/{CIRROS_IMAGES_DIR}/{file_name}"
