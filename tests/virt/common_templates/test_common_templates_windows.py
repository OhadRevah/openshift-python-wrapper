# -*- coding: utf-8 -*-

"""
Common templates test Windows
"""

import logging
import pytest

from resources.datavolume import ImportFromHttpDataVolume
from resources.persistent_volume_claim import PersistentVolumeClaim
from resources.template import Template
from resources.utils import TimeoutSampler
from resources.virtual_machine import VirtualMachine
from tests.virt.common_templates import utils as ct_utils


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def winrmcli_pod(namespace, default_client):
    """
    Deploy winrm-cli Pod into the same namespace.
    """
    with ct_utils.WinRMcliPod(
        name="winrmcli-pod", namespace=namespace.name, client=default_client
    ) as pod:
        pod.wait_for_status(status="Running", timeout=60)
        yield pod


@pytest.fixture(
    params=[
        pytest.param(
            [
                "windows-images/window_qcow2_images/win_10.qcow2",
                "Microsoft Windows 10 Enterprise",
                "win2k12r2-desktop-medium",
                "30Gi",
            ],
            marks=(pytest.mark.polarion("CNV-2196")),
        ),
        pytest.param(
            [
                "windows-images/window_qcow2_images/win_12.qcow2",
                "Microsoft Windows Server 2012 R2 Datacenter",
                "win2k12r2-desktop-medium",
                "30Gi",
            ],
            marks=(pytest.mark.polarion("CNV-2228")),
        ),
    ]
)
def data_volume(request, images_external_http_server, namespace):
    template_name = request.param[2]
    with ct_utils.DataVolumeTestResource(
        name=f"dv-{template_name}",
        namespace=namespace.name,
        url=f"{images_external_http_server}{request.param[0]}",
        os_release=request.param[1],
        template_name=template_name,
        size=request.param[3],
    ) as dv:
        dv.wait_for_status(
            status=ImportFromHttpDataVolume.Status.SUCCEEDED, timeout=300
        )
        assert PersistentVolumeClaim(name=dv.name, namespace=namespace.name).bound()
        yield dv


def test_common_templates_with_windows(winrmcli_pod, data_volume, namespace):
    """
    Test CNV common templates with Windows
    """
    template_instance = Template(name=data_volume.template_name, namespace="openshift")
    resources_list = template_instance.process(
        **{"NAME": data_volume.template_name, "PVCNAME": data_volume.name}
    )
    for resource in resources_list:
        if (
            resource["kind"] == VirtualMachine.kind
            and resource["metadata"]["name"] == data_volume.template_name
        ):
            with ct_utils.VirtualMachineFromTemplate(
                name=data_volume.template_name, namespace=namespace.name, body=resource
            ) as vm:
                vm.start()
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
                    timeout=300, sleep=15, func=winrmcli_pod.execute, command=command
                )
                LOGGER.info(
                    f"Windows VM {vm.vmi.name} booting up, will attempt to access it upto 5 mins."
                )
                for pod_output in pod_output_samples:
                    if data_volume.os_release in str(pod_output):
                        return True
