# -*- coding: utf-8 -*-

"""
Common templates test RHEL
"""

import pytest

import tests.utils
from resources.template import Template
from resources.virtual_machine import VirtualMachine
from tests.utils import get_template_by_labels
from utilities import console


@pytest.fixture(
    params=[
        pytest.param(
            {
                "image": "rhel-images/rhel-76/rhel-76.qcow2",
                "os_release": "7.6",
                "template_labels": [
                    f"{Template.Labels.OS}/rhel7.0",
                    f"{Template.Labels.WORKLOAD}/server",
                    f"{Template.Labels.FLAVOR}/tiny",
                ],
            },
            marks=(pytest.mark.polarion("CNV-2174")),
        ),
        pytest.param(
            {
                "image": "rhel-images/rhel-8/rhel-8.qcow2",
                "os_release": "8.0",
                "template_labels": [
                    f"{Template.Labels.OS}/rhel8.0",
                    f"{Template.Labels.WORKLOAD}/server",
                    f"{Template.Labels.FLAVOR}/tiny",
                ],
            },
            marks=(pytest.mark.polarion("CNV-2210")),
        ),
        pytest.param(
            {
                "image": "rhel-images/rhel-610/rhel-610.qcow2",
                "os_release": "6",
                "template_labels": [
                    f"{Template.Labels.OS}/rhel6.0",
                    f"{Template.Labels.WORKLOAD}/server",
                    f"{Template.Labels.FLAVOR}/tiny",
                ],
            },
            marks=(pytest.mark.polarion("CNV-2211")),
        ),
    ]
)
def data_volume(request, images_external_http_server, namespace):
    template_labels = request.param["template_labels"]
    with tests.utils.DataVolumeTestResource(
        name=f"dv-rhel-{request.param['os_release'].replace(' ', '-').lower()}",
        namespace=namespace.name,
        url=f"{images_external_http_server}{request.param['image']}",
        os_release=request.param["os_release"],
        template_labels=template_labels,
    ) as dv:
        dv.wait(timeout=900)
        yield dv


def test_common_templates_with_rhel(default_client, data_volume, namespace):
    """
    Test CNV common templates with RHEL
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
            with tests.utils.VirtualMachineFromTemplate(
                name=vm_name, namespace=namespace.name, body=resource
            ) as vm:
                vm.start()
                vm.vmi.wait_until_running()
                with console.Fedora(
                    vm=vm, username="cloud-user", password="redhat", timeout=1100
                ) as vm_console:
                    vm_console.sendline(
                        f"cat /etc/redhat-release | grep {data_volume.os_release} | wc -l\n"
                    )
                    vm_console.expect("1", timeout=60)
                vm.stop(wait=True)
