# -*- coding: utf-8 -*-

"""
Common templates test RHEL 7.8
"""

import logging

import pytest
import tests.compute.utils
from tests.compute.ssp.supported_os.common_templates import utils
from utilities import console
from utilities.infra import Images


LOGGER = logging.getLogger(__name__)
VM_NAME = "rhel-7.8"


@pytest.mark.parametrize(
    "data_volume_scope_class, vm_object_from_template_scope_class",
    [
        (
            {
                "image": f"{Images.Rhel.DIR}/{Images.Rhel.RHEL7_8_IMG}",
                "dv_name": f"dv-{VM_NAME}",
            },
            {
                "vm_name": VM_NAME,
                "template_labels": {
                    # TODO: Modify to 7.8 once it is added to templates
                    # https://issues.redhat.com/browse/CNV-3745
                    "os": "rhel7.6",
                    "workload": "server",
                    "flavor": "tiny",
                },
            },
        )
    ],
    indirect=True,
)
class TestCommonTemplatesRhel78:
    @pytest.mark.run("first")
    @pytest.mark.polarion("CNV-3745")
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
    @pytest.mark.polarion("CNV-3749")
    def test_start_vm(
        self,
        skip_upstream,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
    ):
        """ Test CNV common templates VM initiation """

        tests.compute.utils.vm_started(vm=vm_object_from_template_scope_class)

    @pytest.mark.run(after="test_start_vm")
    @pytest.mark.polarion("CNV-3747")
    def test_vm_console(
        self,
        skip_upstream,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
    ):
        """ Test CNV common templates VM console """

        LOGGER.info("Verify VM console connection.")
        utils.wait_for_console(vm_object_from_template_scope_class, console.RHEL)

    @pytest.mark.run(after="test_vm_console")
    @pytest.mark.polarion("CNV-3751")
    def test_os_version(
        self,
        skip_upstream,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
    ):
        """ Test CNV common templates OS version """

        utils.vm_os_version(
            vm=vm_object_from_template_scope_class, console_impl=console.RHEL
        )

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3753")
    def test_domain_label(
        self,
        skip_upstream,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
    ):
        """ CNV common templates 'domain' label contains vm name """

        domain_label = vm_object_from_template_scope_class.instance.spec.template.metadata[
            "labels"
        ][
            "kubevirt.io/domain"
        ]
        assert (
            domain_label == vm_object_from_template_scope_class.name
        ), f"Wrong domain label: {domain_label}"

    @pytest.mark.run(after="test_start_vm")
    @pytest.mark.polarion("CNV-3755")
    def test_expose_ssh(
        self,
        skip_upstream,
        rhel7_workers,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
        vm_ssh_service_scope_class,
        schedulable_node_ips,
    ):
        """ CNV common templates access VM via SSH """

        utils.enable_ssh_service_in_vm(
            vm=vm_object_from_template_scope_class, console_impl=console.RHEL
        )

        assert utils.check_ssh_connection(
            ip=utils.get_vm_accessible_ip(
                rhel7_workers=rhel7_workers,
                schedulable_node_ips=schedulable_node_ips,
                vm=vm_object_from_template_scope_class,
            ),
            port=utils.get_vm_ssh_port(
                rhel7_workers=rhel7_workers, vm=vm_object_from_template_scope_class
            ),
            console_impl=console.RHEL,
        ), "Failed to login via SSH"

    @pytest.mark.run(after="test_expose_ssh")
    @pytest.mark.polarion("CNV-3513")
    def test_guest_agent_info(
        self, vm_object_from_template_scope_class, schedulable_node_ips, rhel7_workers
    ):
        """ Test Guest OS agent info. """
        utils.validate_linux_guest_agent_info(
            vm=vm_object_from_template_scope_class,
            ip=utils.get_vm_accessible_ip(
                rhel7_workers=rhel7_workers,
                schedulable_node_ips=schedulable_node_ips,
                vm=vm_object_from_template_scope_class,
            ),
            ssh_port=utils.get_vm_ssh_port(
                rhel7_workers=rhel7_workers, vm=vm_object_from_template_scope_class
            ),
            username=console.RHEL.USERNAME,
            passwd=console.RHEL.PASSWORD,
        )

    @pytest.mark.run(after="test_start_vm")
    @pytest.mark.polarion("CNV-3767")
    def test_vm_machine_type(
        self,
        skip_upstream,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
    ):
        utils.check_machine_type(vm=vm_object_from_template_scope_class)

    @pytest.mark.run("last")
    @pytest.mark.polarion("CNV-3757")
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
