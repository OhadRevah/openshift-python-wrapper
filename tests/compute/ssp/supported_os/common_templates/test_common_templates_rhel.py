# -*- coding: utf-8 -*-

"""
Common templates test RHEL
"""

import pytest
from resources.template import Template
from utilities import console
from utilities.virt import wait_for_vm_interfaces


@pytest.mark.parametrize(
    "data_volume",
    [
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
                "image": "rhel-images/rhel-81/rhel-81.qcow2",
                "os_release": "8.1",
                "template_labels": [
                    f"{Template.Labels.OS}/rhel8.0",
                    f"{Template.Labels.WORKLOAD}/server",
                    f"{Template.Labels.FLAVOR}/tiny",
                ],
            },
            marks=(pytest.mark.polarion("CNV-3091")),
        ),
    ],
    indirect=True,
)
def test_common_templates_with_rhel(namespace, data_volume, vm_from_template):
    """ Test CNV common templates with RHEL """

    vm_from_template.start(timeout=360, wait=True)
    wait_for_vm_interfaces(vm_from_template.vmi)

    with console.RHEL(vm=vm_from_template, timeout=1100) as vm_console:
        vm_console.sendline(
            f"cat /etc/redhat-release | grep {data_volume.os_release} | wc -l\n"
        )
        vm_console.expect("1", timeout=60)
