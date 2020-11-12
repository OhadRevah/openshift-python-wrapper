# -*- coding: utf-8 -*-

"""
Common templates test RHEL OS support
"""

import logging

import pytest
import tests.compute.ssp.utils as ssp_utils
import utilities.virt
from tests.compute.ssp.supported_os.common_templates import (
    utils as common_templates_utils,
)
from tests.compute.utils import remove_eth0_default_gw, vm_started
from utilities import console
from utilities.infra import BUG_STATUS_CLOSED, get_bug_status
from utilities.virt import check_ssh_connection, wait_for_console


LOGGER = logging.getLogger(__name__)


@pytest.mark.ci
class TestCommonTemplatesRhel:
    @pytest.mark.run("first")
    @pytest.mark.polarion("CNV-3802")
    def test_create_vm(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        rhel_os_matrix__class__,
        data_volume_multi_rhel_os_multi_storage_scope_class,
        vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        """ Test CNV VM creation from template """

        LOGGER.info("Create VM from template.")
        vm_object_from_template_multi_rhel_os_multi_storage_scope_class.create(
            wait=True
        )

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3266")
    def test_start_vm(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        rhel_os_matrix__class__,
        data_volume_multi_rhel_os_multi_storage_scope_class,
        vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        """ Test CNV common templates VM initiation """

        vm_started(
            vm=vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            wait_for_interfaces="rhel-6" not in [*rhel_os_matrix__class__][0],
        )

    @pytest.mark.run(after="test_start_vm")
    @pytest.mark.polarion("CNV-3259")
    def test_vm_console(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        rhel_os_matrix__class__,
        data_volume_multi_rhel_os_multi_storage_scope_class,
        vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        """ Test CNV common templates VM console """

        LOGGER.info("Verify VM console connection.")
        wait_for_console(
            vm=vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            console_impl=console.RHEL,
        )

    @pytest.mark.run(after="test_vm_console")
    @pytest.mark.polarion("CNV-3318")
    def test_os_version(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        rhel_os_matrix__class__,
        data_volume_multi_rhel_os_multi_storage_scope_class,
        vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        """ Test CNV common templates OS version """

        common_templates_utils.vm_os_version(
            vm=vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            console_impl=console.RHEL,
        )

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3306")
    def test_domain_label(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        rhel_os_matrix__class__,
        data_volume_multi_rhel_os_multi_storage_scope_class,
        vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        """ CNV common templates 'domain' label contains vm name """

        domain_label = vm_object_from_template_multi_rhel_os_multi_storage_scope_class.instance.spec.template.metadata[
            "labels"
        ][
            "kubevirt.io/domain"
        ]
        assert (
            domain_label
            == vm_object_from_template_multi_rhel_os_multi_storage_scope_class.name
        ), f"Wrong domain label: {domain_label}"

    @pytest.mark.run(after="test_start_vm")
    @pytest.mark.polarion("CNV-3320")
    def test_expose_ssh(
        self,
        rhel7_workers,
        skip_upstream,
        unprivileged_client,
        namespace,
        rhel_os_matrix__class__,
        data_volume_multi_rhel_os_multi_storage_scope_class,
        vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
        vm_ssh_service_multi_rhel_os_scope_class,
        schedulable_node_ips,
        bugzilla_connection_params,
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
                vm=vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
                console_impl=console.RHEL,
            )

        # OS info is needed for RHEL 7.7 (force-closing console connection)
        if (
            get_bug_status(
                bugzilla_connection_params=bugzilla_connection_params, bug=1886453
            )
            not in BUG_STATUS_CLOSED
            and "rhel-7-7" in [*rhel_os_matrix__class__][0]
        ):
            common_templates_utils.wait_for_guest_os_info(
                vmi=vm_object_from_template_multi_rhel_os_multi_storage_scope_class.vmi
            )

        utilities.virt.enable_ssh_service_in_vm(
            vm=vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            console_impl=console.RHEL,
            systemctl_support="rhel-6" not in [*rhel_os_matrix__class__][0],
        )

        assert check_ssh_connection(
            ip=common_templates_utils.get_vm_accessible_ip(
                rhel7_workers=rhel7_workers,
                schedulable_node_ips=schedulable_node_ips,
                vm=vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            ),
            port=common_templates_utils.get_vm_ssh_port(
                rhel7_workers=rhel7_workers,
                vm=vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            ),
            console_impl=console.RHEL,
        ), "Failed to login via SSH"

    @pytest.mark.run(after="test_expose_ssh")
    @pytest.mark.polarion("CNV-3513")
    def test_vmi_guest_agent_info(
        self,
        skip_upstream,
        skip_guest_agent_on_rhel6,
        rhel_os_matrix__class__,
        schedulable_node_ips,
        rhel7_workers,
        vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        common_templates_utils.validate_os_info_vmi_vs_linux_os(
            vm=vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            ssh_ip=common_templates_utils.get_vm_accessible_ip(
                rhel7_workers=rhel7_workers,
                schedulable_node_ips=schedulable_node_ips,
                vm=vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            ),
            ssh_port=common_templates_utils.get_vm_ssh_port(
                rhel7_workers=rhel7_workers,
                vm=vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            ),
            ssh_usr=console.RHEL.USERNAME,
            ssh_pass=console.RHEL.PASSWORD,
        )

    @pytest.mark.run(after="test_expose_ssh")
    @pytest.mark.polarion("CNV-4195")
    def test_virtctl_guest_agent_os_info(
        self,
        skip_guest_agent_on_rhel6,
        rhel_os_matrix__class__,
        schedulable_node_ips,
        rhel7_workers,
        vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        # TODO: remove restart_qemu_guest_agent_service when cnv moved to RHEL AV 8.3
        common_templates_utils.restart_qemu_guest_agent_service(
            vm=vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            console_impl=console.RHEL,
        )
        common_templates_utils.validate_os_info_virtctl_vs_linux_os(
            vm=vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            ssh_ip=common_templates_utils.get_vm_accessible_ip(
                rhel7_workers=rhel7_workers,
                schedulable_node_ips=schedulable_node_ips,
                vm=vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            ),
            ssh_port=common_templates_utils.get_vm_ssh_port(
                rhel7_workers=rhel7_workers,
                vm=vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            ),
            ssh_usr=console.RHEL.USERNAME,
            ssh_pass=console.RHEL.PASSWORD,
        )

    @pytest.mark.run(after="test_expose_ssh")
    @pytest.mark.polarion("CNV-4550")
    def test_virtctl_guest_agent_user_info(
        self,
        skip_guest_agent_on_rhel6,
        rhel_os_matrix__class__,
        schedulable_node_ips,
        rhel7_workers,
        vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        with console.RHEL(
            vm=vm_object_from_template_multi_rhel_os_multi_storage_scope_class
        ):
            common_templates_utils.validate_user_info_virtctl_vs_linux_os(
                vm=vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
                ssh_ip=common_templates_utils.get_vm_accessible_ip(
                    rhel7_workers=rhel7_workers,
                    schedulable_node_ips=schedulable_node_ips,
                    vm=vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
                ),
                ssh_port=common_templates_utils.get_vm_ssh_port(
                    rhel7_workers=rhel7_workers,
                    vm=vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
                ),
                ssh_usr=console.RHEL.USERNAME,
                ssh_pass=console.RHEL.PASSWORD,
            )

    @pytest.mark.run(after="test_start_vm")
    @pytest.mark.polarion("CNV-3671")
    def test_vm_machine_type(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        rhel_os_matrix__class__,
        data_volume_multi_rhel_os_multi_storage_scope_class,
        vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        common_templates_utils.check_machine_type(
            vm=vm_object_from_template_multi_rhel_os_multi_storage_scope_class
        )

    @pytest.mark.run(after="test_start_vm")
    @pytest.mark.polarion("CNV-4201")
    def test_vm_smbios_default(
        self,
        skip_upstream,
        unprivileged_client,
        smbios_from_kubevirt_config_cm,
        namespace,
        rhel_os_matrix__class__,
        data_volume_multi_rhel_os_multi_storage_scope_class,
        vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        ssp_utils.check_vm_xml_smbios(
            vm=vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            cm_values=smbios_from_kubevirt_config_cm,
        )

    @pytest.mark.run("last")
    @pytest.mark.polarion("CNV-3269")
    def test_vm_deletion(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        rhel_os_matrix__class__,
        data_volume_multi_rhel_os_multi_storage_scope_class,
        vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        """ Test CNV common templates VM deletion """

        if not common_templates_utils.vm_deleted(
            vm=vm_object_from_template_multi_rhel_os_multi_storage_scope_class
        ):
            pytest.xfail("VM was not created, nothing to delete.")
