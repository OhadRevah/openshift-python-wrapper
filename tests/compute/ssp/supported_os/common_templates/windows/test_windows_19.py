# -*- coding: utf-8 -*-

"""
Common templates test Windows 19
"""

import logging

import pytest
import tests.compute.utils
from tests.compute.ssp.supported_os.common_templates import utils
from utilities.infra import BUG_STATUS_CLOSED, Images


LOGGER = logging.getLogger(__name__)
VM_NAME = "win-19"
WIN19_LICENSE_KEY = "N8BP4-3RHM3-YQWTF-MBJC3-YBKQ3"


@pytest.mark.parametrize(
    "data_volume_scope_class, vm_object_from_template_scope_class",
    [
        (
            {
                "image": f"{Images.Windows.DIR}/{Images.Windows.WIN19_IMG}",
                "dv_name": f"dv-{VM_NAME}",
            },
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
class TestCommonTemplatesWin19:
    @pytest.mark.run("first")
    @pytest.mark.polarion("CNV-2816")
    def test_create_vm(
        self,
        skip_upstream,
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
        skip_upstream,
        unprivileged_client,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
        winrmcli_pod_scope_class,
        bridge_attached_helper_vm,
    ):
        """ Test CNV common templates VM initiation """

        tests.compute.utils.vm_started(vm=vm_object_from_template_scope_class)
        utils.wait_for_windows_vm(
            vm=vm_object_from_template_scope_class,
            version=VM_NAME.split("-")[-1],
            winrmcli_pod=winrmcli_pod_scope_class,
            helper_vm=bridge_attached_helper_vm,
        )

    @pytest.mark.run(after="test_start_vm")
    @pytest.mark.polarion("CNV-3512")
    def test_guest_agent_info(
        self,
        vm_object_from_template_scope_class,
        winrmcli_pod_scope_class,
        bridge_attached_helper_vm,
    ):
        """ Test Guest OS agent info. """
        utils.validate_windows_guest_agent_info(
            vm=vm_object_from_template_scope_class,
            winrmcli_pod=winrmcli_pod_scope_class,
            helper_vm=bridge_attached_helper_vm,
        )

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3301")
    @pytest.mark.bugzilla(
        1769692, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    def test_domain_label(
        self,
        skip_upstream,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
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
        skip_upstream,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
        winrmcli_pod_scope_class,
        bridge_attached_helper_vm,
    ):

        LOGGER.info("Verify VM HyperV values.")
        utils.check_vm_xml_hyperv(vm_object_from_template_scope_class)
        utils.check_vm_xml_clock(vm=vm_object_from_template_scope_class)
        utils.check_windows_vm_hvinfo(
            vm=vm_object_from_template_scope_class,
            winrmcli_pod=winrmcli_pod_scope_class,
            helper_vm=bridge_attached_helper_vm,
        )

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3379")
    @pytest.mark.jira("CNV-3771", run=False)
    def test_vm_license_state_after_stop_start(
        self,
        skip_upstream,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
        winrmcli_pod_scope_class,
        bridge_attached_helper_vm,
    ):

        utils.add_activate_windows_license(
            vm=vm_object_from_template_scope_class,
            winrm_pod=winrmcli_pod_scope_class,
            license_key=WIN19_LICENSE_KEY,
            helper_vm=bridge_attached_helper_vm,
        )

        LOGGER.info("Verify VM activation mode is not changed after VM stop/start.")
        utils.check_windows_activated_license(
            vm=vm_object_from_template_scope_class,
            winrmcli_pod=winrmcli_pod_scope_class,
            reset_action="stop_start",
            helper_vm=bridge_attached_helper_vm,
        )

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3417")
    @pytest.mark.jira("CNV-3771", run=False)
    def test_vm_license_state_after_reboot(
        self,
        skip_upstream,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
        winrmcli_pod_scope_class,
        bridge_attached_helper_vm,
    ):

        utils.add_activate_windows_license(
            vm=vm_object_from_template_scope_class,
            winrm_pod=winrmcli_pod_scope_class,
            license_key=WIN19_LICENSE_KEY,
            helper_vm=bridge_attached_helper_vm,
        )

        LOGGER.info("Verify VM activation mode is not changed after reboot.")
        utils.check_windows_activated_license(
            vm=vm_object_from_template_scope_class,
            winrmcli_pod=winrmcli_pod_scope_class,
            reset_action="reboot",
            helper_vm=bridge_attached_helper_vm,
        )

    @pytest.mark.run(after="test_start_vm")
    @pytest.mark.polarion("CNV-3677")
    def test_vm_machine_type(
        self,
        skip_upstream,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
    ):
        utils.check_machine_type(vm=vm_object_from_template_scope_class)

    @pytest.mark.run("last")
    @pytest.mark.polarion("CNV-3291")
    def test_vm_deletion(
        self,
        skip_upstream,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
    ):
        """ Test CNV common templates VM deletion """

        if not utils.vm_deleted(vm=vm_object_from_template_scope_class):
            pytest.xfail("VM was not created, nothing to delete.")
