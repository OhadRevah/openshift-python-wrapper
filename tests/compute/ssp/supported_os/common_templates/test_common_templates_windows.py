# -*- coding: utf-8 -*-

"""
Common templates test Windows
"""

import logging

import pytest
from pytest_testconfig import config as py_config
from resources.template import Template
from resources.utils import TimeoutSampler


LOGGER = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "data_volume_scope_function",
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
            marks=(pytest.mark.polarion("CNV-2196")),
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
            marks=(pytest.mark.polarion("CNV-2228")),
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
            marks=(pytest.mark.polarion("CNV-2175")),
        ),
        pytest.param(
            {
                "image": "windows-images/window_qcow2_images/win_19.qcow2",
                "os_release": "Microsoft Windows Server 2019 Standard",
                "dv_size": "25Gi",
                "template_labels": [
                    f"{Template.Labels.OS}/win2k19",
                    f"{Template.Labels.WORKLOAD}/desktop",
                    f"{Template.Labels.FLAVOR}/medium",
                ],
            },
            marks=(pytest.mark.polarion("CNV-2816")),
        ),
    ],
    indirect=True,
)
@pytest.mark.skipif(
    not py_config["bare_metal_cluster"],
    reason="Running only BM, Reason: windows run slow on nested visualization",
)
def test_common_templates_with_windows(
    namespace, data_volume_scope_function, vm_from_template_scope_function, winrmcli_pod
):
    """ Test CNV common templates with Windows """

    vm_from_template_scope_function.start(wait=True)
    vm_from_template_scope_function.vmi.wait_until_running()

    LOGGER.info(
        f"The value of Windows os_release is {data_volume_scope_function.os_release}"
    )
    vmi_ipaddr = (
        vm_from_template_scope_function.vmi.virt_launcher_pod.instance.status.podIP
    )
    command = [
        "bash",
        "-c",
        f"/bin/winrm-cli -hostname {vmi_ipaddr} \
        -username Administrator -password Heslo123 \
        'wmic os get Caption /value'",
    ]
    pod_output_samples = TimeoutSampler(
        timeout=1500, sleep=15, func=winrmcli_pod.execute, command=command
    )
    LOGGER.info(
        f"Windows VM {vm_from_template_scope_function.name} booting up, will attempt to access it upto 25 mins."
    )
    for pod_output in pod_output_samples:
        if data_volume_scope_function.os_release in str(pod_output):
            return True
