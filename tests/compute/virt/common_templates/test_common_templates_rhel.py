# -*- coding: utf-8 -*-

"""
Common templates test RHEL
"""

import pytest

from resources.template import Template
from resources.virtual_machine import VirtualMachine
from tests.compute.virt.common_templates import utils as ct_utils
from utilities import console

VM_NAME = "virt-common-templates-test"


@pytest.fixture(
    params=[
        pytest.param(
            {
                "image": "rhel-images/rhel-76/rhel-76.qcow2",
                "os_release": "7.6",
                "template_name": "rhel7-server-tiny",
            },
            marks=(pytest.mark.polarion("CNV-2174")),
        ),
        pytest.param(
            {
                "image": "rhel-images/rhel-8/rhel-8.qcow2",
                "os_release": "8.0",
                "template_name": "rhel8-server-tiny",
            },
            marks=(pytest.mark.polarion("CNV-2210")),
        ),
        pytest.param(
            {
                "image": "rhel-images/rhel-610/rhel-610.qcow2",
                "os_release": "6",
                "template_name": "rhel6-server-tiny",
            },
            marks=(pytest.mark.polarion("CNV-2211")),
        ),
    ]
)
def data_volume(request, images_external_http_server, namespace):
    template_name = request.param["template_name"]
    with ct_utils.DataVolumeTestResource(
        name=f"dv-{template_name}",
        namespace=namespace.name,
        url=f"{images_external_http_server}{request.param['image']}",
        os_release=request.param["os_release"],
        template_name=template_name,
    ) as dv:
        dv.wait(timeout=900)
        yield dv


def test_common_templates_with_rhel(data_volume, namespace):
    """
    Test CNV common templates with RHEL
    """
    template_instance = Template(name=data_volume.template_name, namespace="openshift")
    resources_list = template_instance.process(
        **{"NAME": VM_NAME, "PVCNAME": data_volume.name}
    )
    for resource in resources_list:
        if (
            resource["kind"] == VirtualMachine.kind
            and resource["metadata"]["name"] == VM_NAME
        ):
            with ct_utils.VirtualMachineFromTemplate(
                name=VM_NAME, namespace=namespace.name, body=resource
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
