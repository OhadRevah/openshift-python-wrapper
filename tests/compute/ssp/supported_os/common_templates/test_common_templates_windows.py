# -*- coding: utf-8 -*-

"""
Common templates test Windows
"""

import logging

import pytest
import tests.utils
from resources.pod import Pod
from resources.service_account import ServiceAccount
from resources.template import Template
from resources.utils import TimeoutSampler
from resources.virtual_machine import VirtualMachine
from tests.utils import get_template_by_labels


LOGGER = logging.getLogger(__name__)


class WinRMcliPod(Pod):
    def _to_dict(self):
        res = super()._to_dict()
        res["spec"] = {
            "containers": [
                {
                    "name": "winrmcli-con",
                    "image": "kubevirt/winrmcli:latest",
                    "command": ["bash", "-c", "/usr/bin/sleep 6000"],
                }
            ]
        }
        return res


@pytest.fixture(scope="module")
def sa_ready(namespace):
    #  Wait for 'default' service account secrets to be exists.
    #  The Pod creating will fail if we try to create it before.
    default_sa = ServiceAccount(name="default", namespace=namespace.name)
    sampler = TimeoutSampler(
        timeout=10, sleep=1, func=lambda: default_sa.instance.secrets
    )
    for sample in sampler:
        if sample:
            return


@pytest.fixture(scope="module")
def winrmcli_pod(namespace, sa_ready):
    """
    Deploy winrm-cli Pod into the same namespace.
    """
    with WinRMcliPod(name="winrmcli-pod", namespace=namespace.name) as pod:
        pod.wait_for_status(status=pod.Status.RUNNING, timeout=60)
        yield pod


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
    with tests.utils.DataVolumeTestResource(
        name=f"dv-windows-{request.param['os_release'].replace(' ', '-').lower()}",
        namespace=namespace.name,
        url=f"{images_external_http_server}{request.param['os_image']}",
        os_release=request.param["os_release"],
        template_labels=template_labels,
        size=request.param["dv_size"],
    ) as dv:
        dv.wait(timeout=1200)
        yield dv


def test_common_templates_with_windows(
    default_client, winrmcli_pod, data_volume, namespace
):
    """
    Test CNV common templates with Windows
    """
    vm_name = f"{data_volume.name.strip('dv-')}"
    template_instance = get_template_by_labels(
        client=default_client, labels=data_volume.template_labels
    )
    resources_list = template_instance.process(
        **{"NAME": vm_name, "PVCNAME": data_volume.name}
    )
    for resource in resources_list:
        if (
            resource["kind"] == VirtualMachine.kind
            and resource["metadata"]["name"] == vm_name
        ):
            with tests.utils.VirtualMachineForTests(
                name=vm_name, namespace=namespace.name, body=resource
            ) as vm:
                vm.start(wait=True)
                vm.vmi.wait_until_running()
                LOGGER.info(
                    f"The value of Windows os_release is {data_volume.os_release}"
                )
                vmi_ipaddr = vm.vmi.interfaces[0]["ipAddress"]
                command = [
                    "bash",
                    "-c",
                    f"/bin/winrm-cli -hostname {vmi_ipaddr} \
                    -username Administrator -password Heslo123 \
                    'wmic os get Caption /value'",
                ]
                pod_output_samples = TimeoutSampler(
                    timeout=600, sleep=15, func=winrmcli_pod.execute, command=command
                )
                LOGGER.info(
                    f"Windows VM {vm.vmi.name} booting up, will attempt to access it upto 5 mins."
                )
                for pod_output in pod_output_samples:
                    if data_volume.os_release in str(pod_output):
                        return True
