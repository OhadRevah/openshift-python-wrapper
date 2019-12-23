# -*- coding: utf-8 -*-

"""
Common templates test Windows 19
"""

import logging

import pytest
from tests.compute.ssp.supported_os.common_templates import utils
from utilities.infra import BUG_STATUS_CLOSED, Images


LOGGER = logging.getLogger(__name__)
VM_NAME = "win-19"
WIN19_LICENSE_KEY = "N8BP4-3RHM3-YQWTF-MBJC3-YBKQ3"


@pytest.mark.parametrize(
    "data_volume_scope_class, vm_object_from_template_scope_class",
    [
        (
            {"image": Images.Windows.WIN19_IMG, "dv_name": f"dv-{VM_NAME}"},
            {
                "vm_name": VM_NAME,
                "template_labels": {
                    "os": "win2k19",
                    "workload": "server",
                    "flavor": "medium",
                },
                "cpu_threads": 2,
            },
        )
    ],
    indirect=True,
)
@pytest.mark.usefixtures("skip_upstream", "skip_not_bare_metal")
class TestCommonTemplatesWin10:
    @pytest.mark.run("first")
    @pytest.mark.polarion("CNV-2816")
    def test_create_vm(
        self,
        unprivileged_client,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
    ):
        """ Test CNV VM creation from template """

        LOGGER.info("Create VM from template.")
        vm_object_from_template_scope_class.create(wait=True)

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3268")
    def test_start_vm(
        self,
        unprivileged_client,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
        winrmcli_pod_scope_class,
    ):
        """ Test CNV common templates VM initiation """

        utils.vm_started(
            vm=vm_object_from_template_scope_class, wait_for_interfaces=False
        )
        utils.wait_for_windows_vm(
            vm=vm_object_from_template_scope_class,
            version=VM_NAME.split("-")[-1],
            winrmcli_pod=winrmcli_pod_scope_class,
        )

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3301")
    @pytest.mark.bugzilla(
        1769692, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    def test_domain_label(
        self, namespace, data_volume_scope_class, vm_object_from_template_scope_class
    ):
        """ CNV common templates 'domain' label contains vm name """

        domain_label = vm_object_from_template_scope_class.body["spec"]["template"][
            "metadata"
        ]["labels"]["kubevirt.io/domain"]
        assert (
            domain_label == vm_object_from_template_scope_class.name
        ), f"Wrong domain label: {domain_label}"

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-2778")
    def test_hyperv(
        self,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
        winrmcli_pod_scope_class,
    ):

        LOGGER.info("Verify VM HyperV values.")
        utils.check_vm_xml_hyperv(vm_object_from_template_scope_class)
        utils.check_windows_vm_hvinfo(
            vm_object_from_template_scope_class, winrmcli_pod_scope_class
        )

    @pytest.mark.parametrize(
        "activated_vm", [{"license_key": WIN19_LICENSE_KEY}], indirect=True
    )
    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3379")
    def test_vm_license_state_after_stop_start(
        self,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
        winrmcli_pod_scope_class,
        activated_vm,
    ):

        LOGGER.info("Verify VM activation mode is not changed after VM stop/start.")
        utils.check_windows_activated_license(
            vm_object_from_template_scope_class,
            winrmcli_pod_scope_class,
            reset_action="stop_start",
        )

    @pytest.mark.parametrize(
        "activated_vm", [{"license_key": WIN19_LICENSE_KEY}], indirect=True,
    )
    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3417")
    def test_vm_license_state_after_reboot(
        self,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
        winrmcli_pod_scope_class,
        activated_vm,
    ):

        LOGGER.info("Verify VM activation mode is not changed after reboot.")
        utils.check_windows_activated_license(
            vm_object_from_template_scope_class,
            winrmcli_pod_scope_class,
            reset_action="reboot",
        )

    @pytest.mark.run("last")
    @pytest.mark.polarion("CNV-3291")
    def test_vm_deletion(
        self, namespace, data_volume_scope_class, vm_object_from_template_scope_class
    ):
        """ Test CNV common templates VM deletion """

        if not utils.vm_deleted(vm=vm_object_from_template_scope_class):
            pytest.xfail("VM was not created, nothing to delete.")
