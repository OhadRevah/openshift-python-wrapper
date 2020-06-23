# -*- coding: utf-8 -*-

"""
Common templates test Fedora OS support
"""

import logging

import pytest
import utilities.virt
from tests.compute.ssp.supported_os.common_templates import (
    utils as common_templates_utils,
)
from tests.compute.utils import vm_started
from utilities import console
from utilities.infra import BUG_STATUS_CLOSED
from utilities.virt import check_ssh_connection, wait_for_console


LOGGER = logging.getLogger(__name__)


HYPERV_DICT = {
    "spec": {
        "template": {
            "spec": {
                "domain": {
                    "clock": {
                        "utc": {},
                        "timer": {
                            "hpet": {"present": False},
                            "pit": {"tickPolicy": "delay"},
                            "rtc": {"tickPolicy": "catchup"},
                            "hyperv": {},
                        },
                    },
                    "features": {
                        "acpi": {},
                        "apic": {},
                        "hyperv": {
                            "relaxed": {},
                            "vapic": {},
                            "synictimer": {},
                            "vpindex": {},
                            "synic": {},
                            "spinlocks": {"spinlocks": 8191},
                        },
                    },
                }
            }
        }
    }
}


@pytest.mark.parametrize(
    "vm_object_from_template_fedora_os", [({"vm_dict": HYPERV_DICT})], indirect=True,
)
@pytest.mark.smoke
class TestCommonTemplatesFedora:
    @pytest.mark.run("first")
    @pytest.mark.polarion("CNV-3351")
    def test_create_vm(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        fedora_os_matrix__class__,
        data_volume_fedora_os,
        vm_object_from_template_fedora_os,
    ):
        """ Test CNV VM creation from template """

        LOGGER.info("Create VM from template.")
        vm_object_from_template_fedora_os.create(wait=True)

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3345")
    def test_start_vm(
        self,
        skip_upstream,
        namespace,
        fedora_os_matrix__class__,
        data_volume_fedora_os,
        vm_object_from_template_fedora_os,
    ):
        """ Test CNV common templates VM initiation """

        vm_started(vm=vm_object_from_template_fedora_os)

    @pytest.mark.run("test_start_vm")
    @pytest.mark.polarion("CNV-2651")
    def test_vm_hyperv(
        self,
        skip_upstream,
        namespace,
        fedora_os_matrix__class__,
        data_volume_fedora_os,
        vm_object_from_template_fedora_os,
    ):
        LOGGER.info("Verify VMI HyperV values.")
        common_templates_utils.check_vm_xml_hyperv(vm=vm_object_from_template_fedora_os)
        common_templates_utils.check_vm_xml_clock(vm=vm_object_from_template_fedora_os)

    @pytest.mark.run(after="test_start_vm")
    @pytest.mark.polarion("CNV-3344")
    def test_vm_console(
        self,
        skip_upstream,
        namespace,
        fedora_os_matrix__class__,
        data_volume_fedora_os,
        vm_object_from_template_fedora_os,
    ):
        """ Test CNV common templates VM console """

        LOGGER.info("Verify VM console connection.")
        wait_for_console(
            vm=vm_object_from_template_fedora_os, console_impl=console.Fedora
        )

    @pytest.mark.run(after="test_vm_console")
    @pytest.mark.polarion("CNV-3348")
    def test_os_version(
        self,
        skip_upstream,
        namespace,
        fedora_os_matrix__class__,
        data_volume_fedora_os,
        vm_object_from_template_fedora_os,
    ):
        """ Test CNV common templates OS version """

        common_templates_utils.vm_os_version(
            vm=vm_object_from_template_fedora_os, console_impl=console.Fedora
        )

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3347")
    def test_domain_label(
        self,
        skip_upstream,
        namespace,
        fedora_os_matrix__class__,
        data_volume_fedora_os,
        vm_object_from_template_fedora_os,
    ):
        """ CNV common templates 'domain' label contains vm name """

        domain_label = vm_object_from_template_fedora_os.instance.spec.template.metadata[
            "labels"
        ][
            "kubevirt.io/domain"
        ]
        assert (
            domain_label == vm_object_from_template_fedora_os.name
        ), f"Wrong domain label: {domain_label}"

    @pytest.mark.run(after="test_start_vm")
    @pytest.mark.polarion("CNV-3349")
    def test_expose_ssh(
        self,
        skip_upstream,
        rhel7_workers,
        namespace,
        fedora_os_matrix__class__,
        data_volume_fedora_os,
        vm_object_from_template_fedora_os,
        vm_ssh_service_fedora_os,
        schedulable_node_ips,
    ):
        """ CNV common templates access VM via SSH """

        utilities.virt.enable_ssh_service_in_vm(
            vm=vm_object_from_template_fedora_os, console_impl=console.Fedora
        )

        assert check_ssh_connection(
            ip=common_templates_utils.get_vm_accessible_ip(
                rhel7_workers=rhel7_workers,
                schedulable_node_ips=schedulable_node_ips,
                vm=vm_object_from_template_fedora_os,
            ),
            port=common_templates_utils.get_vm_ssh_port(
                rhel7_workers=rhel7_workers, vm=vm_object_from_template_fedora_os
            ),
            console_impl=console.Fedora,
        ), "Failed to login via SSH"

    @pytest.mark.run(after="test_expose_ssh")
    @pytest.mark.polarion("CNV-3937")
    def test_vmi_guest_agent_info(
        self,
        fedora_os_matrix__class__,
        data_volume_fedora_os,
        vm_object_from_template_fedora_os,
        schedulable_node_ips,
        rhel7_workers,
    ):
        """ Test Guest OS agent info. """
        common_templates_utils.validate_vmi_ga_info_vs_linux_os_info(
            vm=vm_object_from_template_fedora_os,
            ssh_ip=common_templates_utils.get_vm_accessible_ip(
                rhel7_workers=rhel7_workers,
                schedulable_node_ips=schedulable_node_ips,
                vm=vm_object_from_template_fedora_os,
            ),
            ssh_port=common_templates_utils.get_vm_ssh_port(
                rhel7_workers=rhel7_workers, vm=vm_object_from_template_fedora_os
            ),
            ssh_usr=console.Fedora.USERNAME,
            ssh_pass=console.Fedora.PASSWORD,
        )

    @pytest.mark.run(after="test_expose_ssh")
    @pytest.mark.polarion("CNV-3573")
    @pytest.mark.bugzilla(
        1845127, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    def test_guest_agent_subresource_os_info(
        self,
        fedora_os_matrix__class__,
        vm_object_from_template_fedora_os,
        schedulable_node_ips,
        rhel7_workers,
        data_volume_fedora_os,
    ):
        common_templates_utils.validate_cnv_os_info_vs_libvirt_os_info(
            vm=vm_object_from_template_fedora_os
        )
        common_templates_utils.validate_cnv_os_info_vs_linux_os_info(
            vm=vm_object_from_template_fedora_os,
            ssh_ip=common_templates_utils.get_vm_accessible_ip(
                rhel7_workers=rhel7_workers,
                schedulable_node_ips=schedulable_node_ips,
                vm=vm_object_from_template_fedora_os,
            ),
            ssh_port=common_templates_utils.get_vm_ssh_port(
                rhel7_workers=rhel7_workers, vm=vm_object_from_template_fedora_os
            ),
            ssh_usr=console.Fedora.USERNAME,
            ssh_pass=console.Fedora.PASSWORD,
        )

    @pytest.mark.run(after="test_expose_ssh")
    @pytest.mark.polarion("CNV-3574")
    def test_guest_agent_subresource_fs_info(
        self,
        fedora_os_matrix__class__,
        vm_object_from_template_fedora_os,
        schedulable_node_ips,
        rhel7_workers,
        data_volume_fedora_os,
    ):
        common_templates_utils.validate_cnv_fs_info_vs_libvirt_fs_info(
            vm=vm_object_from_template_fedora_os
        )
        common_templates_utils.validate_cnv_fs_info_vs_linux_fs_info(
            vm=vm_object_from_template_fedora_os,
            ssh_ip=common_templates_utils.get_vm_accessible_ip(
                rhel7_workers=rhel7_workers,
                schedulable_node_ips=schedulable_node_ips,
                vm=vm_object_from_template_fedora_os,
            ),
            ssh_port=common_templates_utils.get_vm_ssh_port(
                rhel7_workers=rhel7_workers, vm=vm_object_from_template_fedora_os
            ),
            ssh_usr=console.Fedora.USERNAME,
            ssh_pass=console.Fedora.PASSWORD,
        )

    @pytest.mark.run(after="test_start_vm")
    @pytest.mark.polarion("CNV-3668")
    def test_vm_machine_type(
        self,
        fedora_os_matrix__class__,
        skip_upstream,
        namespace,
        data_volume_fedora_os,
        vm_object_from_template_fedora_os,
    ):
        common_templates_utils.check_machine_type(vm=vm_object_from_template_fedora_os)

    @pytest.mark.run("last")
    @pytest.mark.polarion("CNV-3346")
    def test_vm_deletion(
        self,
        skip_upstream,
        namespace,
        fedora_os_matrix__class__,
        data_volume_fedora_os,
        vm_object_from_template_fedora_os,
    ):
        """ Test CNV common templates VM deletion """

        if not common_templates_utils.vm_deleted(vm=vm_object_from_template_fedora_os):
            pytest.xfail("VM was not created, nothing to delete.")
