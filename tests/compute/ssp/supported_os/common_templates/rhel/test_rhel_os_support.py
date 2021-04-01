# -*- coding: utf-8 -*-

"""
Common templates test RHEL OS support
"""

import logging

import pytest

import tests.compute.ssp.utils as ssp_utils
from tests.compute.ssp.supported_os.common_templates import (
    utils as common_templates_utils,
)
from tests.compute.utils import (
    remove_eth0_default_gw,
    validate_libvirt_persistent_domain,
    validate_pause_unpause_linux_vm,
)
from utilities import console
from utilities.infra import BUG_STATUS_CLOSED
from utilities.virt import migrate_and_verify, running_vm, wait_for_console


pytestmark = pytest.mark.post_upgrade


LOGGER = logging.getLogger(__name__)


class TestCommonTemplatesRhel:
    @pytest.mark.dependency(name="create_vm")
    @pytest.mark.polarion("CNV-3802")
    def test_create_vm(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        rhel_os_matrix__class__,
        golden_image_data_volume_multi_rhel_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
        golden_image_vm_ssh_service_multi_rhel_os_scope_class,
    ):
        """ Test CNV VM creation from template """

        LOGGER.info("Create VM from template.")
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class.create(
            wait=True
        )

    @pytest.mark.dependency(name="start_vm", depends=["create_vm"])
    @pytest.mark.polarion("CNV-3266")
    def test_start_vm(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        rhel_os_matrix__class__,
        golden_image_data_volume_multi_rhel_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        """ Test CNV common templates VM initiation """
        guest_agent_support = "rhel-6" not in [*rhel_os_matrix__class__][0]

        running_vm(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            wait_for_interfaces=guest_agent_support,
        )

    @pytest.mark.dependency(depends=["start_vm"])
    @pytest.mark.polarion("CNV-3259")
    def test_vm_console(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        rhel_os_matrix__class__,
        golden_image_data_volume_multi_rhel_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        """ Test CNV common templates VM console """

        LOGGER.info("Verify VM console connection.")
        wait_for_console(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            console_impl=console.RHEL,
        )

    @pytest.mark.dependency(depends=["start_vm"])
    @pytest.mark.polarion("CNV-3318")
    def test_os_version(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        rhel_os_matrix__class__,
        golden_image_data_volume_multi_rhel_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        """ Test CNV common templates OS version """

        common_templates_utils.vm_os_version(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
        )

    @pytest.mark.dependency(depends=["create_vm"])
    @pytest.mark.polarion("CNV-3306")
    def test_domain_label(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        rhel_os_matrix__class__,
        golden_image_data_volume_multi_rhel_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        """ CNV common templates 'domain' label contains vm name """

        label = golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class.instance.spec.template.metadata[  # noqa: E501
            "labels"
        ][
            "kubevirt.io/domain"
        ]
        assert (
            label
            == golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class.name
        ), f"Wrong domain label: {label}"

    @pytest.mark.dependency(name="vm_expose_ssh", depends=["start_vm"])
    @pytest.mark.polarion("CNV-3320")
    def test_expose_ssh(
        self,
        rhel7_workers,
        skip_upstream,
        unprivileged_client,
        namespace,
        rhel_os_matrix__class__,
        golden_image_data_volume_multi_rhel_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        """ CNV common templates access VM via SSH """

        # On RHEL7 VM IP is used for SSH
        if "rhel-6" in [*rhel_os_matrix__class__][0] and rhel7_workers:
            pytest.skip(
                "RHEL6 does not have guest agent, IP cannot be obtained on RHEL 7."
            )

        # On RHEL7, default GW is via eth1. For RHEL8.2, needs to explicitly
        # remove default GW from eth0 after VM is running
        if "rhel-8-2" in [*rhel_os_matrix__class__][0] and rhel7_workers:
            remove_eth0_default_gw(
                vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            )

        assert golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class.ssh_exec.executor().is_connective(  # noqa: E501
            tcp_timeout=120
        ), "Failed to login via SSH"

    @pytest.mark.bugzilla(
        1945703, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    @pytest.mark.dependency(depends=["vm_expose_ssh"])
    @pytest.mark.polarion("CNV-3513")
    def test_vmi_guest_agent_info(
        self,
        skip_upstream,
        skip_guest_agent_on_rhel6,
        rhel_os_matrix__class__,
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        common_templates_utils.validate_os_info_vmi_vs_linux_os(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class
        )

    @pytest.mark.dependency(depends=["vm_expose_ssh"])
    @pytest.mark.polarion("CNV-4195")
    def test_virtctl_guest_agent_os_info(
        self,
        skip_guest_agent_on_rhel6,
        rhel_os_matrix__class__,
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        # TODO: remove restart_qemu_guest_agent_service when cnv moved to newer qemu versions
        common_templates_utils.restart_qemu_guest_agent_service(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
        )
        common_templates_utils.validate_os_info_virtctl_vs_linux_os(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class
        )

    @pytest.mark.dependency(depends=["vm_expose_ssh"])
    @pytest.mark.polarion("CNV-4550")
    def test_virtctl_guest_agent_user_info(
        self,
        skip_guest_agent_on_rhel6,
        rhel_os_matrix__class__,
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        with console.RHEL(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class
        ):
            common_templates_utils.validate_user_info_virtctl_vs_linux_os(
                vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class
            )

    @pytest.mark.dependency(depends=["start_vm"])
    @pytest.mark.polarion("CNV-3671")
    def test_vm_machine_type(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        rhel_os_matrix__class__,
        golden_image_data_volume_multi_rhel_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        common_templates_utils.check_machine_type(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class
        )

    @pytest.mark.dependency(depends=["start_vm"])
    @pytest.mark.polarion("CNV-4201")
    def test_vm_smbios_default(
        self,
        skip_upstream,
        unprivileged_client,
        smbios_from_kubevirt_config,
        namespace,
        rhel_os_matrix__class__,
        golden_image_data_volume_multi_rhel_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        ssp_utils.check_vm_xml_smbios(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            cm_values=smbios_from_kubevirt_config,
        )

    @pytest.mark.dependency(depends=["start_vm"])
    @pytest.mark.polarion("CNV-5916")
    def test_pause_unpause_vm(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        rhel_os_matrix__class__,
        golden_image_data_volume_multi_rhel_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        validate_pause_unpause_linux_vm(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
        )

    @pytest.mark.polarion("CNV-3038")
    @pytest.mark.dependency(name="migrate_vm", depends=["vm_expose_ssh"])
    def test_migrate_vm(
        self,
        skip_upstream,
        skip_access_mode_rwo_scope_function,
        unprivileged_client,
        namespace,
        rhel_os_matrix__class__,
        golden_image_data_volume_multi_rhel_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
        ping_process_in_rhel_os,
    ):
        """ Test SSH connectivity after migration"""
        migrate_and_verify(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            check_ssh_connectivity=True,
        )
        validate_libvirt_persistent_domain(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class
        )

    @pytest.mark.polarion("CNV-5902")
    @pytest.mark.dependency(depends=["migrate_vm"])
    def test_pause_unpause_after_migrate(
        self,
        skip_upstream,
        skip_access_mode_rwo_scope_function,
        unprivileged_client,
        namespace,
        rhel_os_matrix__class__,
        golden_image_data_volume_multi_rhel_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
        ping_process_in_rhel_os,
    ):
        validate_pause_unpause_linux_vm(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            pre_pause_pid=ping_process_in_rhel_os,
        )

    @pytest.mark.dependency(depends=["create_vm"])
    @pytest.mark.polarion("CNV-3269")
    def test_vm_deletion(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        rhel_os_matrix__class__,
        golden_image_data_volume_multi_rhel_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        """ Test CNV common templates VM deletion """
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class.delete(
            wait=True
        )
