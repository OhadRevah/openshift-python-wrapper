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
from tests.compute.utils import remove_eth0_default_gw
from utilities import console
from utilities.infra import BUG_STATUS_CLOSED
from utilities.virt import running_vm, wait_for_console


LOGGER = logging.getLogger(__name__)


@pytest.mark.ci
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

        running_vm(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            wait_for_interfaces="rhel-6" not in [*rhel_os_matrix__class__][0],
        )

    @pytest.mark.dependency(name="vm_console", depends=["start_vm"])
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

    @pytest.mark.dependency(depends=["vm_console"])
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
            console_impl=console.RHEL,
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
                console_impl=console.RHEL,
            )

        assert golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class.ssh_exec.executor().is_connective(  # noqa: E501
            tcp_timeout=120
        ), "Failed to login via SSH"

    @pytest.mark.bugzilla(
        1883875, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
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

    @pytest.mark.bugzilla(
        1883875, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
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

    @pytest.mark.bugzilla(
        1883875, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
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
        smbios_from_kubevirt_config_cm,
        namespace,
        rhel_os_matrix__class__,
        golden_image_data_volume_multi_rhel_os_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        ssp_utils.check_vm_xml_smbios(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            cm_values=smbios_from_kubevirt_config_cm,
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
