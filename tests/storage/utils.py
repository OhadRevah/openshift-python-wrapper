# -*- coding: utf-8 -*-

import logging
import os
import urllib.request

import requests
import tests.utils
from pytest_testconfig import config as py_config
from resources.pod import Pod
from resources.route import Route
from resources.virtual_machine import VirtualMachine
from utilities import console, utils


LOGGER = logging.getLogger(__name__)


CLOUD_INIT_USER_DATA = r"""
            #!/bin/sh
            echo 'printed from cloud-init userdata'"""


class VirtualMachineWithDV(VirtualMachine):
    def __init__(self, name, namespace, dv_name, cloud_init_data, client=None):
        super().__init__(name=name, namespace=namespace, client=client)
        self._dv_name = dv_name
        self._cloud_init_data = cloud_init_data

    def _to_dict(self):
        res = super()._to_dict()

        spec = res["spec"]["template"]["spec"]
        spec["domain"]["devices"]["disks"] = [
            {"disk": {"bus": "virtio"}, "name": "dv-disk"},
            {"disk": {"bus": "virtio"}, "name": "cloudinitdisk"},
        ]

        spec["volumes"] = [
            {
                "name": "cloudinitdisk",
                "cloudInitNoCloud": {"userData": self._cloud_init_data},
            },
            {"name": "dv-disk", "dataVolume": {"name": self._dv_name}},
        ]
        return res


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


def create_vm_with_dv(dv):
    with VirtualMachineWithDV(
        name="cirros-vm",
        namespace=dv.namespace,
        dv_name=dv.name,
        cloud_init_data=CLOUD_INIT_USER_DATA,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        with console.Cirros(vm=vm) as vm_console:
            vm_console.sendline("lsblk | grep disk | wc -l")
            vm_console.expect("2", timeout=60)


def virtctl_upload(namespace, pvc_name, pvc_size, image_path):
    return utils.run_virtctl_command(
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
    url = f"{tests.utils.get_images_external_http_server()}{remote_name}"
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
