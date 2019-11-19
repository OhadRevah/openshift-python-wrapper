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
from resources.utils import TimeoutSampler
from utilities.infra import Images


LOGGER = logging.getLogger(__name__)
PASSWORD = "Heslo123"
USERNAME = "Administrator"
WINRMCLI = f"/bin/winrm-cli -username {USERNAME} -password {PASSWORD}"


@pytest.fixture()
def download_hvinfo(winrmcli_pod_scope_module):
    server_name = py_config[py_config["region"]]["http_server"]
    binary_url = os.path.join(server_name, "binaries/hvinfo/hvinfo.exe")
    download_hvinfo_cmd = ["bash", "-c", f"curl -OL {binary_url}"]
    winrmcli_pod_scope_module.execute(download_hvinfo_cmd, timeout=30)


@pytest.mark.parametrize(
    "data_volume_scope_function, vm_instance_from_template_scope_function",
    [
        pytest.param(
            {
                "image": Images.Windows.WIM10_IMG,
                "dv_name": "dv-win-10",
                "dv_size": "30Gi",
            },
            {
                "vm_name": "win-10",
                "template_labels": {
                    "os": "win10",
                    "workload": "desktop",
                    "flavor": "medium",
                },
                "start_vm": True,
                "guest_agent": False,
            },
            marks=pytest.mark.polarion("CNV-2776"),
            id="test_windows10_hyperv",
        ),
        pytest.param(
            {
                "image": Images.Windows.WIN12_IMG,
                "dv_name": "dv-win-12",
                "dv_size": "25Gi",
            },
            {
                "vm_name": "win-12",
                "template_labels": {
                    "os": "win2k12r2",
                    "workload": "desktop",
                    "flavor": "medium",
                },
                "start_vm": True,
                "guest_agent": False,
            },
            marks=pytest.mark.polarion("CNV-2652"),
            id="test_windows2012R2_hyperv",
        ),
        pytest.param(
            {
                "image": Images.Windows.WIN16_IMG,
                "dv_name": "dv-win-16",
                "dv_size": "30Gi",
            },
            {
                "vm_name": "win-16",
                "template_labels": {
                    "os": "win2k16",
                    "workload": "desktop",
                    "flavor": "medium",
                },
                "start_vm": True,
                "guest_agent": False,
            },
            marks=pytest.mark.polarion("CNV-2777"),
            id="test_windows2016_hyperv",
        ),
        pytest.param(
            {
                "image": Images.Windows.WIN19_IMG,
                "dv_name": "dv-win-19",
                "dv_size": "25Gi",
            },
            {
                "vm_name": "win-19",
                "template_labels": {
                    "os": "win2k19",
                    "workload": "desktop",
                    "flavor": "medium",
                },
                "start_vm": True,
                "guest_agent": False,
            },
            marks=pytest.mark.polarion("CNV-2778"),
            id="test_windows2019_hyperv",
        ),
    ],
    indirect=True,
)
@pytest.mark.skipif(
    py_config["distribution"] == "upstream",
    reason="Running only on downstream, Reason: http_server is not available for upstream",
)
@pytest.mark.skipif(
    not py_config["bare_metal_cluster"],
    reason="Running only BM, Reason: windows run slow on nested visualization",
)
def test_windows_hyperv(
    namespace,
    data_volume_scope_function,
    vm_instance_from_template_scope_function,
    winrmcli_pod_scope_module,
    download_hvinfo,
):
    """ Windows test: check hyperV """
    windows_vmi = vm_instance_from_template_scope_function.vmi
    windows_vmi.wait_until_running()

    features = windows_vmi.xml_dict["domain"]["features"]
    hyperv = features["hyperv"]
    assert hyperv["relaxed"]["@state"] == "on"
    assert hyperv["vapic"]["@state"] == "on"
    assert int(hyperv["spinlocks"]["@retries"]) == 8191

    vmi_ipaddr = windows_vmi.virt_launcher_pod.instance.status.podIP
    command = [
        "bash",
        "-c",
        f"{WINRMCLI} -hostname {vmi_ipaddr} \
        'wmic os get Caption /value'",
    ]
    pod_output_samples = TimeoutSampler(
        timeout=1800, sleep=15, func=winrmcli_pod_scope_module.execute, command=command
    )
    LOGGER.info(
        f"Windows VM {vm_instance_from_template_scope_function.name} "
        f"booting up, will attempt to access it upto 30 mins."
    )
    for pod_output in pod_output_samples:
        if vm_instance_from_template_scope_function.name.split("-")[-1] in str(
            pod_output
        ):
            copy_hvinfo_cmd = [
                "bash",
                "-c",
                f"/usr/bin/winrmcp -user={USERNAME} \
                -pass={PASSWORD} -addr={vmi_ipaddr}:5985  \
                /hvinfo.exe C:\\hvinfo.exe",
            ]
            winrmcli_pod_scope_module.execute(copy_hvinfo_cmd, timeout=600)
            LOGGER.info(
                f"Copied the binary hvinfo.exe into the Windows VM \
                {vm_instance_from_template_scope_function.name} successfully."
            )
            run_hvinfo_cmd = [
                "bash",
                "-c",
                f"{WINRMCLI} -hostname {vmi_ipaddr} \
                C:\\hvinfo.exe",
            ]
            hvinfo = winrmcli_pod_scope_module.execute(run_hvinfo_cmd, timeout=20)
            hvinfo_dict = json.loads(hvinfo)

            assert hvinfo_dict["HyperVsupport"]
            assert hvinfo_dict["Recommendations"]["RelaxedTiming"]
            assert hvinfo_dict["Recommendations"]["MSRAPICRegisters"]
            assert int(hvinfo_dict["Recommendations"]["SpinlockRetries"]) == 8191
