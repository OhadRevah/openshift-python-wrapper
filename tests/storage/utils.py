# -*- coding: utf-8 -*-

import logging
import os
import urllib.request
from contextlib import contextmanager

import requests
from pytest_testconfig import config as py_config
from resources.pod import Pod
from resources.route import Route
from resources.service import Service
from utilities import console
from utilities.infra import get_images_external_http_server
from utilities.virt import VirtualMachineForTests, run_virtctl_command


LOGGER = logging.getLogger(__name__)


class PodWithPVC(Pod):
    def __init__(self, name, namespace, pvc_name):
        super().__init__(name=name, namespace=namespace)
        self._pvc_name = pvc_name

    def _to_dict(self):
        res = super()._to_dict()

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
                            "volumeMounts": [
                                {"mountPath": "/pvc", "name": self._pvc_name}
                            ],
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


def check_disk_count_in_vm_with_dv(vm):
    with console.Cirros(vm=vm) as vm_console:
        LOGGER.info(f"Check disk count.")
        vm_console.sendline("lsblk | grep disk | wc -l")
        vm_console.expect("2", timeout=60)


@contextmanager
def create_vm_with_dv(dv, image=None):
    with VirtualMachineForTests(
        name="cirros-vm", namespace=dv.namespace, dv=dv.name, image=image
    ) as vm:
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
