# -*- coding: utf-8 -*-

"""
Common templates test Windows
"""

import logging

import pytest
from pytest_testconfig import config as py_config
from resources.template import Template
from resources.utils import TimeoutSampler
from utilities.storage import DataVolumeTestResource
from utilities.virt import VirtualMachineForTestsFromTemplate


LOGGER = logging.getLogger(__name__)


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
            marks=(pytest.mark.polarion("CNV-2196")),
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
            marks=(pytest.mark.polarion("CNV-2228")),
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
            marks=(pytest.mark.polarion("CNV-2175")),
        ),
        pytest.param(
            {
                "os_image": "windows-images/window_qcow2_images/win_19.qcow2",
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
    ]
)
def data_volume(request, images_external_http_server, namespace):
    template_labels = request.param["template_labels"]
    with DataVolumeTestResource(
        name=f"dv-windows-{request.param['os_release'].replace(' ', '-').lower()}",
        namespace=namespace.name,
        url=f"{images_external_http_server}{request.param['os_image']}",
        os_release=request.param["os_release"],
        template_labels=template_labels,
        size=request.param["dv_size"],
        storage_class=py_config["storage_defaults"]["storage_class"],
    ) as dv:
        dv.wait(timeout=1200)
        yield dv


@pytest.fixture()
def windows_vm(unprivileged_client, data_volume, namespace):
    """
    Create Windows VM with CNV common templates.
    """
    vm_name = f"{data_volume.name.strip('dv-')}"
    with VirtualMachineForTestsFromTemplate(
        name=vm_name,
        namespace=namespace.name,
        client=unprivileged_client,
        labels=data_volume.template_labels,
        template_dv=data_volume.name,
    ) as vm:
        yield vm


@pytest.mark.skipif(
    not py_config["bare_metal_cluster"],
    reason="Running only BM, Reason: windows run slow on nested visualization",
)
def test_common_templates_with_windows(winrmcli_pod, data_volume, windows_vm):
    """
    Test CNV common templates with Windows
    """
    windows_vm.start()
    windows_vm.vmi.wait_until_running()
    LOGGER.info(f"The value of Windows os_release is {data_volume.os_release}")
    vmi_ipaddr = windows_vm.vmi.interfaces[0]["ipAddress"]
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
        f"Windows VM {windows_vm.name} booting up, will attempt to access it upto 25 mins."
    )
    for pod_output in pod_output_samples:
        if data_volume.os_release in str(pod_output):
            return True
