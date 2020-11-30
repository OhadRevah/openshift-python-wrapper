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
    "vm_object_from_template_multi_fedora_os_multi_storage_scope_class",
    [({"vm_dict": HYPERV_DICT})],
    indirect=True,
)
@pytest.mark.ocp_interop
class TestCommonTemplatesFedora:
    @pytest.mark.smoke
    @pytest.mark.dependency(name="create_vm")
    @pytest.mark.polarion("CNV-3351")
    def test_create_vm(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        fedora_os_matrix__class__,
        data_volume_multi_fedora_os_multi_storage_scope_class,
        vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
    ):
        """ Test CNV VM creation from template """

        LOGGER.info("Create VM from template.")
        vm_object_from_template_multi_fedora_os_multi_storage_scope_class.create(
            wait=True
        )

    @pytest.mark.smoke
    @pytest.mark.dependency(name="start_vm", depends=["create_vm"])
    @pytest.mark.polarion("CNV-3345")
    def test_start_vm(
        self,
        skip_upstream,
        namespace,
        fedora_os_matrix__class__,
        data_volume_multi_fedora_os_multi_storage_scope_class,
        vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
    ):
        """ Test CNV common templates VM initiation """

        vm_started(vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class)

    @pytest.mark.dependency(depends=["start_vm"])
    @pytest.mark.polarion("CNV-2651")
    def test_vm_hyperv(
        self,
        skip_upstream,
        namespace,
        fedora_os_matrix__class__,
        data_volume_multi_fedora_os_multi_storage_scope_class,
        vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
    ):
        LOGGER.info("Verify VMI HyperV values.")
        common_templates_utils.check_vm_xml_hyperv(
            vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class
        )
        common_templates_utils.check_vm_xml_clock(
            vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class
        )

    @pytest.mark.smoke
    @pytest.mark.dependency(name="vm_console", depends=["start_vm"])
    @pytest.mark.polarion("CNV-3344")
    def test_vm_console(
        self,
        skip_upstream,
        namespace,
        fedora_os_matrix__class__,
        data_volume_multi_fedora_os_multi_storage_scope_class,
        vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
    ):
        """ Test CNV common templates VM console """

        LOGGER.info("Verify VM console connection.")
        wait_for_console(
            vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
            console_impl=console.Fedora,
        )

    @pytest.mark.dependency(depends=["vm_console"])
    @pytest.mark.polarion("CNV-3348")
    def test_os_version(
        self,
        skip_upstream,
        namespace,
        fedora_os_matrix__class__,
        data_volume_multi_fedora_os_multi_storage_scope_class,
        vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
    ):
        """ Test CNV common templates OS version """

        common_templates_utils.vm_os_version(
            vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
            console_impl=console.Fedora,
        )

    @pytest.mark.dependency(depends=["create_vm"])
    @pytest.mark.polarion("CNV-3347")
    def test_domain_label(
        self,
        skip_upstream,
        namespace,
        fedora_os_matrix__class__,
        data_volume_multi_fedora_os_multi_storage_scope_class,
        vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
    ):
        """ CNV common templates 'domain' label contains vm name """
        vm = vm_object_from_template_multi_fedora_os_multi_storage_scope_class
        domain_label = vm.instance.spec.template.metadata["labels"][
            "kubevirt.io/domain"
        ]
        assert domain_label == vm.name, f"Wrong domain label: {domain_label}"

    @pytest.mark.smoke
    @pytest.mark.dependency(name="vm_expose_ssh", depends=["start_vm"])
    @pytest.mark.polarion("CNV-3349")
    def test_expose_ssh(
        self,
        skip_upstream,
        rhel7_workers,
        namespace,
        fedora_os_matrix__class__,
        data_volume_multi_fedora_os_multi_storage_scope_class,
        vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
        vm_ssh_service_multi_fedora_os_scope_class,
        schedulable_node_ips,
    ):
        """ CNV common templates access VM via SSH """

        utilities.virt.enable_ssh_service_in_vm(
            vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
            console_impl=console.Fedora,
        )

        assert check_ssh_connection(
            ip=common_templates_utils.get_vm_accessible_ip(
                rhel7_workers=rhel7_workers,
                schedulable_node_ips=schedulable_node_ips,
                vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
            ),
            port=common_templates_utils.get_vm_ssh_port(
                rhel7_workers=rhel7_workers,
                vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
            ),
            console_impl=console.Fedora,
        ), "Failed to login via SSH"

    @pytest.mark.smoke
    @pytest.mark.dependency(depends=["vm_expose_ssh"])
    @pytest.mark.polarion("CNV-3937")
    def test_vmi_guest_agent_info(
        self,
        fedora_os_matrix__class__,
        schedulable_node_ips,
        rhel7_workers,
        vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
    ):
        """ Test Guest OS agent info. """
        common_templates_utils.validate_os_info_vmi_vs_linux_os(
            vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
            ssh_ip=common_templates_utils.get_vm_accessible_ip(
                rhel7_workers=rhel7_workers,
                schedulable_node_ips=schedulable_node_ips,
                vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
            ),
            ssh_port=common_templates_utils.get_vm_ssh_port(
                rhel7_workers=rhel7_workers,
                vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
            ),
            ssh_usr=console.Fedora.USERNAME,
            ssh_pass=console.Fedora.PASSWORD,
        )

    @pytest.mark.bugzilla(
        1883875, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    @pytest.mark.dependency(depends=["vm_expose_ssh"])
    @pytest.mark.polarion("CNV-3573")
    def test_virtctl_guest_agent_os_info(
        self,
        fedora_os_matrix__class__,
        schedulable_node_ips,
        rhel7_workers,
        vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
    ):
        # TODO: remove restart_qemu_guest_agent_service when cnv moved to RHEL AV 8.3
        common_templates_utils.restart_qemu_guest_agent_service(
            vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
            console_impl=console.Fedora,
        )
        common_templates_utils.validate_os_info_virtctl_vs_linux_os(
            vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
            ssh_ip=common_templates_utils.get_vm_accessible_ip(
                rhel7_workers=rhel7_workers,
                schedulable_node_ips=schedulable_node_ips,
                vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
            ),
            ssh_port=common_templates_utils.get_vm_ssh_port(
                rhel7_workers=rhel7_workers,
                vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
            ),
            ssh_usr=console.Fedora.USERNAME,
            ssh_pass=console.Fedora.PASSWORD,
        )

    @pytest.mark.bugzilla(
        1883875, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    @pytest.mark.dependency(depends=["vm_expose_ssh"])
    @pytest.mark.polarion("CNV-3574")
    def test_virtctl_guest_agent_fs_info(
        self,
        fedora_os_matrix__class__,
        schedulable_node_ips,
        rhel7_workers,
        vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
    ):
        common_templates_utils.validate_fs_info_virtctl_vs_linux_os(
            vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
            ssh_ip=common_templates_utils.get_vm_accessible_ip(
                rhel7_workers=rhel7_workers,
                schedulable_node_ips=schedulable_node_ips,
                vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
            ),
            ssh_port=common_templates_utils.get_vm_ssh_port(
                rhel7_workers=rhel7_workers,
                vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
            ),
            ssh_usr=console.Fedora.USERNAME,
            ssh_pass=console.Fedora.PASSWORD,
        )

    @pytest.mark.bugzilla(
        1883875, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    @pytest.mark.dependency(depends=["vm_expose_ssh"])
    @pytest.mark.polarion("CNV-4549")
    def test_virtctl_guest_agent_user_info(
        self,
        fedora_os_matrix__class__,
        schedulable_node_ips,
        rhel7_workers,
        vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
    ):
        with console.Fedora(
            vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class
        ):
            common_templates_utils.validate_user_info_virtctl_vs_linux_os(
                vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
                ssh_ip=common_templates_utils.get_vm_accessible_ip(
                    rhel7_workers=rhel7_workers,
                    schedulable_node_ips=schedulable_node_ips,
                    vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
                ),
                ssh_port=common_templates_utils.get_vm_ssh_port(
                    rhel7_workers=rhel7_workers,
                    vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
                ),
                ssh_usr=console.Fedora.USERNAME,
                ssh_pass=console.Fedora.PASSWORD,
            )

    @pytest.mark.dependency(depends=["start_vm"])
    @pytest.mark.polarion("CNV-3668")
    def test_vm_machine_type(
        self,
        fedora_os_matrix__class__,
        skip_upstream,
        namespace,
        data_volume_multi_fedora_os_multi_storage_scope_class,
        vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
    ):
        common_templates_utils.check_machine_type(
            vm=vm_object_from_template_multi_fedora_os_multi_storage_scope_class
        )

    @pytest.mark.smoke
    @pytest.mark.dependency(depends=["create_vm"])
    @pytest.mark.polarion("CNV-3346")
    def test_vm_deletion(
        self,
        skip_upstream,
        namespace,
        fedora_os_matrix__class__,
        data_volume_multi_fedora_os_multi_storage_scope_class,
        vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
    ):
        """ Test CNV common templates VM deletion """
        vm_object_from_template_multi_fedora_os_multi_storage_scope_class.delete(
            wait=True
        )
