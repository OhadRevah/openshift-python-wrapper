# -*- coding: utf-8 -*-

"""
Common templates test CentOS support
"""

import logging

import pytest

import tests.compute.ssp.utils as ssp_utils
from tests.compute.ssp.supported_os.common_templates import (
    utils as common_templates_utils,
)
from utilities import console
from utilities.infra import BUG_STATUS_CLOSED
from utilities.virt import running_vm, wait_for_console


LOGGER = logging.getLogger(__name__)


class TestCommonTemplatesCentos:
    @pytest.mark.dependency(name="create_vm")
    @pytest.mark.polarion("CNV-5337")
    def test_create_vm(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        centos_os_matrix__class__,
        golden_image_data_volume_multi_centos_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
        golden_image_vm_ssh_service_multi_centos_scope_class,
    ):
        """ Test CNV VM creation from template """

        LOGGER.info("Create VM from template.")
        golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class.create(
            wait=True
        )

    @pytest.mark.dependency(name="start_vm", depends=["create_vm"])
    @pytest.mark.polarion("CNV-5338")
    def test_start_vm(
        self,
        skip_upstream,
        namespace,
        centos_os_matrix__class__,
        golden_image_data_volume_multi_centos_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
    ):
        """ Test CNV common templates VM initiation """

        running_vm(
            vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class
        )

    @pytest.mark.dependency(name="vm_console", depends=["start_vm"])
    @pytest.mark.polarion("CNV-5341")
    def test_vm_console(
        self,
        skip_upstream,
        namespace,
        centos_os_matrix__class__,
        golden_image_data_volume_multi_centos_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
    ):
        """ Test CNV common templates VM console """

        LOGGER.info("Verify VM console connection.")
        wait_for_console(
            vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
            console_impl=console.Centos,
        )

    @pytest.mark.dependency(depends=["vm_console"])
    @pytest.mark.polarion("CNV-5342")
    def test_os_version(
        self,
        skip_upstream,
        namespace,
        centos_os_matrix__class__,
        golden_image_data_volume_multi_centos_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
    ):
        """ Test CNV common templates OS version """

        common_templates_utils.vm_os_version(
            vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
            console_impl=console.Centos,
        )

    @pytest.mark.dependency(depends=["create_vm"])
    @pytest.mark.polarion("CNV-5344")
    def test_domain_label(
        self,
        skip_upstream,
        namespace,
        centos_os_matrix__class__,
        golden_image_data_volume_multi_centos_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
    ):
        """ CNV common templates 'domain' label contains vm name """
        vm = golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class
        domain_label = vm.instance.spec.template.metadata["labels"][
            "kubevirt.io/domain"
        ]
        assert domain_label == vm.name, f"Wrong domain label: {domain_label}"

    @pytest.mark.dependency(name="vm_expose_ssh", depends=["start_vm"])
    @pytest.mark.polarion("CNV-5345")
    def test_expose_ssh(
        self,
        skip_upstream,
        rhel7_workers,
        namespace,
        centos_os_matrix__class__,
        golden_image_data_volume_multi_centos_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
    ):
        """ CNV common templates access VM via SSH """

        assert golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class.ssh_exec.executor().is_connective(  # noqa: E501
            tcp_timeout=120
        ), "Failed to login via SSH"

    @pytest.mark.bugzilla(
        1883875, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    @pytest.mark.dependency(depends=["vm_expose_ssh"])
    @pytest.mark.polarion("CNV-5346")
    def test_vmi_guest_agent_info(
        self,
        centos_os_matrix__class__,
        schedulable_node_ips,
        rhel7_workers,
        golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
    ):
        """ Test Guest OS agent info. """
        common_templates_utils.validate_os_info_vmi_vs_linux_os(
            vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class
        )

    @pytest.mark.bugzilla(
        1883875, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    @pytest.mark.dependency(depends=["vm_expose_ssh"])
    @pytest.mark.polarion("CNV-5347")
    def test_virtctl_guest_agent_os_info(
        self,
        centos_os_matrix__class__,
        schedulable_node_ips,
        rhel7_workers,
        golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
    ):
        # TODO: remove restart_qemu_guest_agent_service when cnv moved to newer qemu versions
        common_templates_utils.restart_qemu_guest_agent_service(
            vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
        )
        common_templates_utils.validate_os_info_virtctl_vs_linux_os(
            vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class
        )

    @pytest.mark.bugzilla(
        1883875, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    @pytest.mark.dependency(depends=["vm_expose_ssh"])
    @pytest.mark.polarion("CNV-5348")
    def test_virtctl_guest_agent_fs_info(
        self,
        centos_os_matrix__class__,
        schedulable_node_ips,
        rhel7_workers,
        golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
    ):
        common_templates_utils.validate_fs_info_virtctl_vs_linux_os(
            vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class
        )

    @pytest.mark.bugzilla(
        1883875, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    @pytest.mark.dependency(depends=["vm_expose_ssh"])
    @pytest.mark.polarion("CNV-5349")
    def test_virtctl_guest_agent_user_info(
        self,
        centos_os_matrix__class__,
        schedulable_node_ips,
        rhel7_workers,
        golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
    ):
        with console.Centos(
            vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class
        ):
            common_templates_utils.validate_user_info_virtctl_vs_linux_os(
                vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class
            )

    @pytest.mark.dependency(depends=["start_vm"])
    @pytest.mark.polarion("CNV-5350")
    def test_vm_machine_type(
        self,
        centos_os_matrix__class__,
        skip_upstream,
        namespace,
        golden_image_data_volume_multi_centos_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
    ):
        common_templates_utils.check_machine_type(
            vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class
        )

    @pytest.mark.dependency(depends=["start_vm"])
    @pytest.mark.polarion("CNV-5594")
    def test_vm_smbios_default(
        self,
        smbios_from_kubevirt_config_cm,
        namespace,
        golden_image_data_volume_multi_centos_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
    ):
        ssp_utils.check_vm_xml_smbios(
            vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
            cm_values=smbios_from_kubevirt_config_cm,
        )

    @pytest.mark.dependency(depends=["create_vm"])
    @pytest.mark.polarion("CNV-5351")
    def test_vm_deletion(
        self,
        skip_upstream,
        namespace,
        centos_os_matrix__class__,
        golden_image_data_volume_multi_centos_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
    ):
        """ Test CNV common templates VM deletion """
        golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class.delete(
            wait=True
        )
