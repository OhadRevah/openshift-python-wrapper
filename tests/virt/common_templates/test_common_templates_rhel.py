# -*- coding: utf-8 -*-

"""
Common templates test RHEL
"""

import pytest

from resources.datavolume import ImportFromHttpDataVolume
from resources.persistent_volume_claim import PersistentVolumeClaim
from resources.template import Template
from resources.virtual_machine import VirtualMachine
from tests.virt.common_templates import utils as ct_utils
from utilities import console

VM_NAME = "virt-common-templates-test"


@pytest.fixture(
    params=[
        pytest.param(
            ["rhel-images/rhel-76/rhel-76.qcow2", "7.6", "rhel7-server-tiny"],
            marks=(pytest.mark.polarion("CNV-2174")),
        ),
        pytest.param(
            ["rhel-images/rhel-8/rhel-8.qcow2", "8.0", "rhel8-server-tiny"],
            marks=(pytest.mark.polarion("CNV-2210")),
        ),
        pytest.param(
            ["rhel-images/rhel-610/rhel-610.qcow2", "6", "rhel6-server-tiny"],
            marks=(pytest.mark.polarion("CNV-2211")),
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
    ) as dv:
        dv.wait_for_status(
            status=ImportFromHttpDataVolume.Status.SUCCEEDED, timeout=300
        )
        assert PersistentVolumeClaim(name=dv.name, namespace=namespace.name).bound()
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
