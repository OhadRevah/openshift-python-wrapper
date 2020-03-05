# -*- coding: utf-8 -*-

"""
Common templates test Windows OS support
"""
import logging

import pytest
import tests.compute.utils
from tests.compute.ssp.supported_os.common_templates import utils
from utilities.infra import BUG_STATUS_CLOSED


LOGGER = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "vm_object_from_template_windows_os", [({"cpu_threads": 2})], indirect=True,
)
@pytest.mark.usefixtures(
    "skip_upstream", "unprivileged_client", "namespace", "data_volume_windows_os"
)
class TestCommonTemplatesWindows:
    @pytest.mark.run("first")
    @pytest.mark.polarion("CNV-2196")
    def test_create_vm(self, vm_object_from_template_windows_os):
        """ Test CNV VM creation from template """

        LOGGER.info("Create VM from template.")
        vm_object_from_template_windows_os.create(wait=True)

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3785")
    def test_start_vm(
        self,
        vm_object_from_template_windows_os,
        winrmcli_pod_scope_class,
        bridge_attached_helper_vm,
    ):
        """ Test CNV common templates VM initiation """

        tests.compute.utils.vm_started(vm=vm_object_from_template_windows_os)
        utils.wait_for_windows_vm(
            vm=vm_object_from_template_windows_os,
            version=vm_object_from_template_windows_os.name.split("-")[-1],
            winrmcli_pod=winrmcli_pod_scope_class,
            helper_vm=bridge_attached_helper_vm,
        )

    @pytest.mark.run(after="test_start_vm")
    @pytest.mark.polarion("CNV-3512")
    def test_guest_agent_info(
        self,
        vm_object_from_template_windows_os,
        winrmcli_pod_scope_class,
        bridge_attached_helper_vm,
    ):
        """ Test Guest OS agent info. """
        utils.validate_windows_guest_agent_info(
            vm=vm_object_from_template_windows_os,
            winrmcli_pod=winrmcli_pod_scope_class,
            helper_vm=bridge_attached_helper_vm,
        )

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3303")
    @pytest.mark.bugzilla(
        1769692, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    def test_domain_label(
        self, vm_object_from_template_windows_os,
    ):
        """ CNV common templates 'domain' label contains vm name """

        domain_label = vm_object_from_template_windows_os.body["spec"]["template"][
            "metadata"
        ]["labels"]["kubevirt.io/domain"]
        assert (
            domain_label == vm_object_from_template_windows_os.name
        ), f"Wrong domain label: {domain_label}"

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-2776")
    def test_hyperv(
        self,
        vm_object_from_template_windows_os,
        winrmcli_pod_scope_class,
        bridge_attached_helper_vm,
    ):

        LOGGER.info("Verify VM HyperV values.")
        utils.check_vm_xml_hyperv(vm_object_from_template_windows_os)
        utils.check_windows_vm_hvinfo(
            vm=vm_object_from_template_windows_os,
            winrmcli_pod=winrmcli_pod_scope_class,
            helper_vm=bridge_attached_helper_vm,
        )

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-2177")
    @pytest.mark.jira("CNV-3771", run=False)
    def test_vm_license_state_after_stop_start(
        self,
        vm_object_from_template_windows_os,
        winrmcli_pod_scope_class,
        bridge_attached_helper_vm,
        windows_os_matrix,
    ):

        utils.add_activate_windows_license(
            vm=vm_object_from_template_windows_os,
            winrm_pod=winrmcli_pod_scope_class,
            license_key=windows_os_matrix[[*windows_os_matrix][0]]["license"],
            helper_vm=bridge_attached_helper_vm,
        )

        LOGGER.info("Verify VM activation mode is not changed after VM stop/start.")
        utils.check_windows_activated_license(
            vm=vm_object_from_template_windows_os,
            winrmcli_pod=winrmcli_pod_scope_class,
            reset_action="stop_start",
            helper_vm=bridge_attached_helper_vm,
        )

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3415")
    @pytest.mark.jira("CNV-3771", run=False)
    def test_vm_license_state_after_reboot(
        self,
        vm_object_from_template_windows_os,
        winrmcli_pod_scope_class,
        bridge_attached_helper_vm,
        windows_os_matrix,
    ):

        utils.add_activate_windows_license(
            vm=vm_object_from_template_windows_os,
            winrm_pod=winrmcli_pod_scope_class,
            license_key=windows_os_matrix[[*windows_os_matrix][0]]["license"],
            helper_vm=bridge_attached_helper_vm,
        )

        LOGGER.info("Verify VM activation mode is not changed after reboot.")
        utils.check_windows_activated_license(
            vm=vm_object_from_template_windows_os,
            winrmcli_pod=winrmcli_pod_scope_class,
            reset_action="reboot",
            helper_vm=bridge_attached_helper_vm,
        )

    @pytest.mark.run(after="test_start_vm")
    @pytest.mark.polarion("CNV-3674")
    def test_vm_machine_type(
        self, vm_object_from_template_windows_os,
    ):
        utils.check_machine_type(vm=vm_object_from_template_windows_os)

    @pytest.mark.run("last")
    @pytest.mark.polarion("CNV-3289")
    def test_vm_deletion(
        self, vm_object_from_template_windows_os,
    ):
        """ Test CNV common templates VM deletion """

        if not utils.vm_deleted(vm=vm_object_from_template_windows_os):
            pytest.xfail("VM was not created, nothing to delete.")
