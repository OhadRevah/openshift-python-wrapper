# -*- coding: utf-8 -*-

"""
Common templates test Windows OS support
"""
import logging

import pytest
import tests.compute.utils
import utilities.virt
from tests.compute.ssp.supported_os.common_templates import utils
from utilities.infra import BUG_STATUS_CLOSED
from utilities.virt import validate_windows_guest_agent_info


LOGGER = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "vm_object_from_template_windows_os", [({"cpu_threads": 2})], indirect=True,
)
class TestCommonTemplatesWindows:
    @pytest.mark.run("first")
    @pytest.mark.polarion("CNV-2196")
    def test_create_vm(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        windows_os_matrix__class__,
        data_volume_windows_os,
        vm_object_from_template_windows_os,
    ):
        """ Test CNV VM creation from template """

        LOGGER.info("Create VM from template.")
        vm_object_from_template_windows_os.create(wait=True)

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3785")
    def test_start_vm(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        windows_os_matrix__class__,
        data_volume_windows_os,
        vm_object_from_template_windows_os,
        winrmcli_pod_scope_class,
        bridge_attached_helper_vm,
    ):
        """ Test CNV common templates VM initiation """

        tests.compute.utils.vm_started(vm=vm_object_from_template_windows_os)
        utilities.virt.wait_for_windows_vm(
            vm=vm_object_from_template_windows_os,
            version=windows_os_matrix__class__[[*windows_os_matrix__class__][0]][
                "os_version"
            ],
            winrmcli_pod=winrmcli_pod_scope_class,
            helper_vm=bridge_attached_helper_vm,
        )

    @pytest.mark.run(after="test_start_vm")
    @pytest.mark.polarion("CNV-3512")
    def test_guest_agent_info(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        windows_os_matrix__class__,
        data_volume_windows_os,
        vm_object_from_template_windows_os,
        winrmcli_pod_scope_class,
        bridge_attached_helper_vm,
    ):
        """ Test Guest OS agent info. """
        validate_windows_guest_agent_info(
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
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        windows_os_matrix__class__,
        data_volume_windows_os,
        vm_object_from_template_windows_os,
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
        skip_upstream,
        unprivileged_client,
        namespace,
        windows_os_matrix__class__,
        data_volume_windows_os,
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
        skip_upstream,
        unprivileged_client,
        namespace,
        windows_os_matrix__class__,
        data_volume_windows_os,
        vm_object_from_template_windows_os,
        winrmcli_pod_scope_class,
        bridge_attached_helper_vm,
    ):

        utils.add_activate_windows_license(
            vm=vm_object_from_template_windows_os,
            winrm_pod=winrmcli_pod_scope_class,
            license_key=windows_os_matrix__class__[[*windows_os_matrix__class__][0]][
                "license"
            ],
            helper_vm=bridge_attached_helper_vm,
        )

        LOGGER.info("Verify VM activation mode is not changed after VM stop/start.")
        utils.check_windows_activated_license(
            vm=vm_object_from_template_windows_os,
            winrmcli_pod=winrmcli_pod_scope_class,
            reset_action="stop_start",
            version=windows_os_matrix__class__[[*windows_os_matrix__class__][0]][
                "os_version"
            ],
            helper_vm=bridge_attached_helper_vm,
        )

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3415")
    @pytest.mark.jira("CNV-3771", run=False)
    def test_vm_license_state_after_reboot(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        windows_os_matrix__class__,
        data_volume_windows_os,
        vm_object_from_template_windows_os,
        winrmcli_pod_scope_class,
        bridge_attached_helper_vm,
    ):

        utils.add_activate_windows_license(
            vm=vm_object_from_template_windows_os,
            winrm_pod=winrmcli_pod_scope_class,
            license_key=windows_os_matrix__class__[[*windows_os_matrix__class__][0]][
                "license"
            ],
            helper_vm=bridge_attached_helper_vm,
        )

        LOGGER.info("Verify VM activation mode is not changed after reboot.")
        utils.check_windows_activated_license(
            vm=vm_object_from_template_windows_os,
            winrmcli_pod=winrmcli_pod_scope_class,
            reset_action="reboot",
            version=windows_os_matrix__class__[[*windows_os_matrix__class__][0]][
                "os_version"
            ],
            helper_vm=bridge_attached_helper_vm,
        )

    @pytest.mark.run(after="test_start_vm")
    @pytest.mark.polarion("CNV-3674")
    def test_vm_machine_type(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        windows_os_matrix__class__,
        data_volume_windows_os,
        vm_object_from_template_windows_os,
    ):
        utils.check_machine_type(vm=vm_object_from_template_windows_os)

    @pytest.mark.run("last")
    @pytest.mark.polarion("CNV-3289")
    def test_vm_deletion(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        windows_os_matrix__class__,
        data_volume_windows_os,
        vm_object_from_template_windows_os,
    ):
        """ Test CNV common templates VM deletion """

        if not utils.vm_deleted(vm=vm_object_from_template_windows_os):
            pytest.xfail("VM was not created, nothing to delete.")
