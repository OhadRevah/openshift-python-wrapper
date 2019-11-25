# -*- coding: utf-8 -*-

"""
Common templates test Windows 10
"""

import logging

import pytest
from tests.compute.ssp.supported_os.common_templates import utils
from utilities.infra import BUG_STATUS_CLOSED, Images


LOGGER = logging.getLogger(__name__)
VM_NAME = "win-10"


@pytest.mark.parametrize(
    "data_volume_scope_class, vm_object_from_template",
    [
        (
            {
                "image": Images.Windows.WIM10_IMG,
                "dv_name": f"dv-{VM_NAME}",
                "dv_size": "30Gi",
            },
            {
                "vm_name": VM_NAME,
                "template_labels": {
                    "os": "win10",
                    "workload": "desktop",
                    "flavor": "medium",
                },
            },
        )
    ],
    indirect=True,
)
@pytest.mark.usefixtures("skip_upstream", "skip_not_bare_metal")
class TestCommonTemplatesWin10:
    @pytest.mark.run("first")
    @pytest.mark.polarion("CNV-2174")
    def test_create_vm(
        self,
        unprivileged_client,
        namespace,
        data_volume_scope_class,
        vm_object_from_template,
    ):
        """ Test CNV VM creation from template """

        LOGGER.info("Create VM from template.")
        vm_object_from_template.create(wait=True)

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-2196")
    def test_start_vm(
        self,
        unprivileged_client,
        namespace,
        data_volume_scope_class,
        vm_object_from_template,
        winrmcli_pod_scope_class,
    ):
        """ Test CNV common templates VM initiation """

        utils.vm_started(vm=vm_object_from_template, wait_for_interfaces=False)
        utils.wait_for_windows_vm(
            vm=vm_object_from_template,
            version=VM_NAME.split("-")[-1],
            winrmcli_pod=winrmcli_pod_scope_class,
        )

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3303")
    @pytest.mark.bugzilla(
        1769692, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    def test_domain_label(
        self, namespace, data_volume_scope_class, vm_object_from_template
    ):
        """ CNV common templates 'domain' label contains vm name """

        domain_label = vm_object_from_template.body["spec"]["template"]["metadata"][
            "labels"
        ]["kubevirt.io/domain"]
        assert (
            domain_label == vm_object_from_template.name
        ), f"Wrong domain label: {domain_label}"

    @pytest.mark.run("last")
    @pytest.mark.polarion("CNV-3289")
    def test_vm_deletion(
        self, namespace, data_volume_scope_class, vm_object_from_template
    ):
        """ Test CNV common templates VM deletion """

        if not utils.vm_deleted(vm=vm_object_from_template):
            pytest.xfail("VM was not created, nothing to delete.")
