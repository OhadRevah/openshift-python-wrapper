# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV virt common-templates tests
"""

import json
import logging
import os

import pytest
from pytest_testconfig import config as py_config
from resources.template import Template
from resources.utils import TimeoutSampler
from utilities.infra import BUG_STATUS_CLOSED
from utilities.storage import DataVolumeTestResource
from utilities.virt import VirtualMachineForTestsFromTemplate


LOGGER = logging.getLogger(__name__)
PASSWORD = "Heslo123"
USERNAME = "Administrator"
WINRMCLI = f"/bin/winrm-cli -username {USERNAME} -password {PASSWORD}"


@pytest.fixture(
    params=[
        pytest.param(
            {
                "os_image": "windows-images/window_qcow2_images/win_10.qcow2",
                "os_release": "Microsoft Windows 10 Enterprise",
                "dv_size": "30Gi",
                "template_labels": [
                    f"{Template.Labels.OS}/win10",
                    f"{Template.Labels.WORKLOAD}/desktop",
                    f"{Template.Labels.FLAVOR}/medium",
                ],
            },
            marks=(
                pytest.mark.polarion("CNV-2776"),
                pytest.mark.bugzilla(
                    1663162, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
            ),
        ),
        pytest.param(
            {
                "os_image": "windows-images/window_qcow2_images/win_12.qcow2",
                "os_release": "Microsoft Windows Server 2012 R2 Datacenter",
                "dv_size": "25Gi",
                "template_labels": [
                    f"{Template.Labels.OS}/win2k12r2",
                    f"{Template.Labels.WORKLOAD}/desktop",
                    f"{Template.Labels.FLAVOR}/medium",
                ],
            },
            marks=(
                pytest.mark.polarion("CNV-2652"),
                pytest.mark.bugzilla(
                    1663162, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
            ),
        ),
        pytest.param(
            {
                "os_image": "windows-images/window_qcow2_images/win_16.qcow2",
                "os_release": "Microsoft Windows Server 2016 Datacenter",
                "dv_size": "30Gi",
                "template_labels": [
                    f"{Template.Labels.OS}/win2k16",
                    f"{Template.Labels.WORKLOAD}/desktop",
                    f"{Template.Labels.FLAVOR}/medium",
                ],
            },
            marks=(
                pytest.mark.polarion("CNV-2777"),
                pytest.mark.bugzilla(
                    1663162, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
            ),
        ),
        pytest.param(
            {
                "os_image": "windows-images/window_qcow2_images/win_16.qcow2",
                "os_release": "Microsoft Windows Server 2019 Standard",
                "dv_size": "25Gi",
                "template_labels": [
                    f"{Template.Labels.OS}/win2k19",
                    f"{Template.Labels.WORKLOAD}/desktop",
                    f"{Template.Labels.FLAVOR}/medium",
                ],
            },
            marks=(
                pytest.mark.polarion("CNV-2778"),
                pytest.mark.bugzilla(
                    1663162, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
            ),
        ),
    ]
)
def data_volume(request, images_external_http_server, windows_namespace):
    with DataVolumeTestResource(
        name=f"dv-windows-{request.param['os_release'].replace(' ', '-').lower()}",
        namespace=windows_namespace.name,
        url=f"{images_external_http_server}{request.param['os_image']}",
        os_release=request.param["os_release"],
        template_labels=request.param["template_labels"],
        size=request.param["dv_size"],
        storage_class=py_config["storage_defaults"]["storage_class"],
    ) as dv:
        dv.wait()
        yield dv


@pytest.fixture()
def windows_vm(default_client, data_volume, windows_namespace):
    """
    Create Windows VM with CNV common templates.
    """
    vm_name = f"{data_volume.name.strip('dv-')}"
    with VirtualMachineForTestsFromTemplate(
        name=vm_name,
        namespace=windows_namespace.name,
        client=default_client,
        labels=data_volume.template_labels,
        template_dv=data_volume.name,
    ) as vm:
        yield vm


@pytest.fixture()
def download_hvinfo(winrmcli_pod):
    server_name = py_config[py_config["region"]]["http_server"]
    base_url = os.path.join(server_name, "binaries")
    binary_url = os.path.join(base_url, "hvinfo/hvinfo.exe")
    download_hvinfo_cmd = ["bash", "-c", f"curl -OL {binary_url}"]
    winrmcli_pod.execute(download_hvinfo_cmd, timeout=30)


def test_windows_hyperv(winrmcli_pod, data_volume, windows_vm, download_hvinfo):
    """
    Test CNV common templates with Windows
    """
    windows_vm.start()
    windows_vm.vmi.wait_until_running()
    vmi_ipaddr = windows_vm.vmi.interfaces[0]["ipAddress"]
    command = [
        "bash",
        "-c",
        f"{WINRMCLI} -hostname {vmi_ipaddr} \
        'wmic os get Caption /value'",
    ]
    pod_output_samples = TimeoutSampler(
        timeout=600, sleep=15, func=winrmcli_pod.execute, command=command
    )
    LOGGER.info(
        f"Windows VM {windows_vm.name} booting up, will attempt to access it upto 10 mins."
    )
    for pod_output in pod_output_samples:
        if data_volume.os_release in str(pod_output):
            copy_hvinfo_cmd = [
                "bash",
                "-c",
                f"/usr/bin/winrmcp -user={USERNAME} \
                -pass={PASSWORD} -addr={vmi_ipaddr}:5985  \
                /hvinfo.exe C:\\hvinfo.exe",
            ]
            winrmcli_pod.execute(copy_hvinfo_cmd, timeout=600)
            run_hvinfo_cmd = [
                "bash",
                "-c",
                f"{WINRMCLI} -hostname {vmi_ipaddr} \
                C:\\hvinfo.exe",
            ]
            hvinfo = winrmcli_pod.execute(run_hvinfo_cmd, timeout=20)
            hvinfo_dict = json.loads(hvinfo)
            assert hvinfo_dict["HyperVsupport"]
