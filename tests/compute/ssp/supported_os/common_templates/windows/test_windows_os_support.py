# -*- coding: utf-8 -*-

"""
Common templates test Windows OS support
"""
import logging

import pytest
from pytest_testconfig import config as py_config

import tests.compute.ssp.utils as ssp_utils
import utilities.virt
from tests.compute import utils as compute_utils
from tests.compute.ssp.supported_os.common_templates import (
    utils as common_templates_utils,
)
from utilities.infra import BUG_STATUS_CLOSED


LOGGER = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class",
    [
        (
            {
                "cpu_threads": 2,
                "ssh": True,
                "username": py_config["windows_username"],
                "password": py_config["windows_password"],
            }
        )
    ],
    indirect=True,
)
class TestCommonTemplatesWindows:
    @pytest.mark.dependency(name="create_vm")
    @pytest.mark.polarion("CNV-2196")
    def test_create_vm(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        windows_os_matrix__class__,
        golden_image_data_volume_multi_windows_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
    ):
        """ Test CNV VM creation from template """

        LOGGER.info("Create VM from template.")
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class.create(
            wait=True
        )

    @pytest.mark.dependency(name="start_vm", depends=["create_vm"])
    @pytest.mark.polarion("CNV-3785")
    def test_start_vm(
        self,
        skip_upstream,
        windows_os_matrix__class__,
        golden_image_data_volume_multi_windows_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
    ):
        """ Test CNV common templates VM initiation """

        compute_utils.vm_started(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class
        )
        utilities.virt.wait_for_windows_vm(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
            version=windows_os_matrix__class__[[*windows_os_matrix__class__][0]][
                "os_version"
            ],
        )

    @pytest.mark.bugzilla(
        1883875, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    @pytest.mark.dependency(depends=["start_vm"])
    @pytest.mark.polarion("CNV-3512")
    def test_vmi_guest_agent_info(
        self,
        windows_os_matrix__class__,
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
    ):
        """ Test Guest OS agent info. """
        common_templates_utils.validate_os_info_vmi_vs_windows_os(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
        )

    @pytest.mark.bugzilla(
        1883875, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    @pytest.mark.dependency(depends=["start_vm"])
    @pytest.mark.polarion("CNV-4196")
    def test_virtctl_guest_agent_os_info(
        self,
        skip_guest_agent_on_win12,
        windows_os_matrix__class__,
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
    ):
        common_templates_utils.validate_os_info_virtctl_vs_windows_os(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
        )

    @pytest.mark.bugzilla(
        1883875, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    @pytest.mark.dependency(depends=["start_vm"])
    @pytest.mark.polarion("CNV-4197")
    def test_virtctl_guest_agent_fs_info(
        self,
        skip_guest_agent_on_win12,
        windows_os_matrix__class__,
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
    ):
        common_templates_utils.validate_fs_info_virtctl_vs_windows_os(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
        )

    @pytest.mark.bugzilla(
        1883875, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    @pytest.mark.dependency(depends=["start_vm"])
    @pytest.mark.polarion("CNV-4552")
    def test_virtctl_guest_agent_user_info(
        self,
        skip_guest_agent_on_win12,
        windows_os_matrix__class__,
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
    ):
        common_templates_utils.validate_user_info_virtctl_vs_windows_os(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
        )

    @pytest.mark.dependency(depends=["create_vm"])
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
        golden_image_data_volume_multi_windows_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
    ):
        """ CNV common templates 'domain' label contains vm name """
        vm = golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class
        domain_label = vm.body["spec"]["template"]["metadata"]["labels"][
            "kubevirt.io/domain"
        ]
        assert domain_label == vm.name, f"Wrong domain label: {domain_label}"

    @pytest.mark.dependency(depends=["start_vm"])
    @pytest.mark.polarion("CNV-2776")
    def test_hyperv(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        windows_os_matrix__class__,
        golden_image_data_volume_multi_windows_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
    ):

        LOGGER.info("Verify VM HyperV values.")
        common_templates_utils.check_vm_xml_hyperv(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class
        )
        common_templates_utils.check_windows_vm_hvinfo(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
        )

    @pytest.mark.dependency(depends=["start_vm"])
    @pytest.mark.polarion("CNV-2177")
    @pytest.mark.jira("CNV-3771", run=False)
    def test_vm_license_state_after_stop_start(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        windows_os_matrix__class__,
        golden_image_data_volume_multi_windows_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
    ):

        common_templates_utils.add_activate_windows_license(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
            license_key=windows_os_matrix__class__[[*windows_os_matrix__class__][0]][
                "license"
            ],
        )

        LOGGER.info("Verify VM activation mode is not changed after VM stop/start.")
        common_templates_utils.check_windows_activated_license(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
            reset_action="stop_start",
            version=windows_os_matrix__class__[[*windows_os_matrix__class__][0]][
                "os_version"
            ],
        )

    @pytest.mark.dependency(depends=["start_vm"])
    @pytest.mark.polarion("CNV-3415")
    @pytest.mark.jira("CNV-3771", run=False)
    def test_vm_license_state_after_reboot(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        windows_os_matrix__class__,
        golden_image_data_volume_multi_windows_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
    ):

        common_templates_utils.add_activate_windows_license(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
            license_key=windows_os_matrix__class__[[*windows_os_matrix__class__][0]][
                "license"
            ],
        )

        LOGGER.info("Verify VM activation mode is not changed after reboot.")
        common_templates_utils.check_windows_activated_license(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
            reset_action="reboot",
            version=windows_os_matrix__class__[[*windows_os_matrix__class__][0]][
                "os_version"
            ],
        )

    @pytest.mark.dependency(depends=["start_vm"])
    @pytest.mark.polarion("CNV-3674")
    def test_vm_machine_type(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        windows_os_matrix__class__,
        golden_image_data_volume_multi_windows_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
    ):
        common_templates_utils.check_machine_type(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class
        )

    @pytest.mark.dependency(depends=["start_vm"])
    @pytest.mark.polarion("CNV-3087")
    def test_pause_unpause_vm(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        windows_os_matrix__class__,
        golden_image_data_volume_multi_windows_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
    ):
        """ Test VM pause and unpause """

        pre_pause_processid = compute_utils.start_and_fetch_processid_on_windows_vm(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
            process_name="mspaint.exe",
        )
        LOGGER.info(f"Pre pause processid is: {pre_pause_processid}")
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class.vmi.pause(
            wait=True
        )

        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class.vmi.unpause(
            wait=True
        )

        utilities.virt.wait_for_windows_vm(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
            version=windows_os_matrix__class__[[*windows_os_matrix__class__][0]][
                "os_version"
            ],
        )
        post_pause_processid = compute_utils.fetch_processid_from_windows_vm(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
            process_name="mspaint.exe",
        )
        LOGGER.info(f"Post pause processid is: {post_pause_processid}")
        assert pre_pause_processid == post_pause_processid

    @pytest.mark.dependency(depends=["start_vm"])
    @pytest.mark.polarion("CNV-4203")
    def test_vm_smbios_default(
        self,
        skip_upstream,
        unprivileged_client,
        smbios_from_kubevirt_config_cm,
        namespace,
        windows_os_matrix__class__,
        golden_image_data_volume_multi_windows_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
    ):
        ssp_utils.check_vm_xml_smbios(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
            cm_values=smbios_from_kubevirt_config_cm,
        )

    @pytest.mark.dependency(depends=["create_vm"])
    @pytest.mark.polarion("CNV-3289")
    def test_vm_deletion(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        windows_os_matrix__class__,
        golden_image_data_volume_multi_windows_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
    ):
        """ Test CNV common templates VM deletion """
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class.delete(
            wait=True
        )
