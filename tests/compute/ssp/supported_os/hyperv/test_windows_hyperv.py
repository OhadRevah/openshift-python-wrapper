# -*- coding: utf-8 -*-

"""
[SSP] hyperv feature - checking VMI XML
This test case includes only windows based test case
"""

import json
import logging
import os

import pytest
from pytest_testconfig import config as py_config
from resources.template import Template
from resources.utils import TimeoutSampler
from utilities.infra import BUG_STATUS_CLOSED


LOGGER = logging.getLogger(__name__)
PASSWORD = "Heslo123"
USERNAME = "Administrator"
WINRMCLI = f"/bin/winrm-cli -username {USERNAME} -password {PASSWORD}"


@pytest.fixture()
def download_hvinfo(winrmcli_pod):
    server_name = py_config[py_config["region"]]["http_server"]
    binary_url = os.path.join(server_name, "binaries/hvinfo/hvinfo.exe")
    download_hvinfo_cmd = ["bash", "-c", f"curl -OL {binary_url}"]
    winrmcli_pod.execute(download_hvinfo_cmd, timeout=30)


@pytest.mark.parametrize(
    "data_volume_scope_function, vm_from_template_scope_function",
    [
        pytest.param(
            {
                "image": "windows-images/window_qcow2_images/win_10.qcow2",
                "os_release": "Microsoft Windows 10 Enterprise",
                "dv_size": "30Gi",
                "template_labels": [
                    f"{Template.Labels.OS}/win10",
                    f"{Template.Labels.WORKLOAD}/desktop",
                    f"{Template.Labels.FLAVOR}/medium",
                ],
            },
            {"start_vm": True, "guest_agent": False},
            marks=(
                pytest.mark.polarion("CNV-2776"),
                pytest.mark.bugzilla(
                    1663162, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
            ),
        ),
        pytest.param(
            {
                "image": "windows-images/window_qcow2_images/win_12.qcow2",
                "os_release": "Microsoft Windows Server 2012 R2 Datacenter",
                "dv_size": "25Gi",
                "template_labels": [
                    f"{Template.Labels.OS}/win2k12r2",
                    f"{Template.Labels.WORKLOAD}/desktop",
                    f"{Template.Labels.FLAVOR}/medium",
                ],
            },
            {"start_vm": True, "guest_agent": False},
            marks=(
                pytest.mark.polarion("CNV-2652"),
                pytest.mark.bugzilla(
                    1663162, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
            ),
        ),
        pytest.param(
            {
                "image": "windows-images/window_qcow2_images/win_16.qcow2",
                "os_release": "Microsoft Windows Server 2016 Datacenter",
                "dv_size": "30Gi",
                "template_labels": [
                    f"{Template.Labels.OS}/win2k16",
                    f"{Template.Labels.WORKLOAD}/desktop",
                    f"{Template.Labels.FLAVOR}/medium",
                ],
            },
            {"start_vm": True, "guest_agent": False},
            marks=(
                pytest.mark.polarion("CNV-2777"),
                pytest.mark.bugzilla(
                    1663162, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
            ),
        ),
        pytest.param(
            {
                "image": "windows-images/window_qcow2_images/win_16.qcow2",
                "os_release": "Microsoft Windows Server 2019 Standard",
                "dv_size": "25Gi",
                "template_labels": [
                    f"{Template.Labels.OS}/win2k19",
                    f"{Template.Labels.WORKLOAD}/desktop",
                    f"{Template.Labels.FLAVOR}/medium",
                ],
            },
            {"start_vm": True, "guest_agent": False},
            marks=(
                pytest.mark.polarion("CNV-2778"),
                pytest.mark.bugzilla(
                    1663162, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
            ),
        ),
    ],
    indirect=True,
)
@pytest.mark.skipif(
    py_config["distribution"] == "upstream",
    reason="Running only on downstream, Reason: http_server is not available for upstream",
)
def test_windows_hyperv(
    namespace,
    data_volume_scope_function,
    vm_from_template_scope_function,
    winrmcli_pod,
    download_hvinfo,
):
    """ Windows test: check hyperV """

    vmi_ipaddr = vm_from_template_scope_function.vmi.interfaces[0]["ipAddress"]
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
        f"Windows VM {vm_from_template_scope_function.name} booting up, will attempt to access it upto 10 mins."
    )
    for pod_output in pod_output_samples:
        if data_volume_scope_function.os_release in str(pod_output):
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
