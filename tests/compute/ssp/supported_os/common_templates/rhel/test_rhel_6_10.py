# -*- coding: utf-8 -*-

"""
Common templates test RHEL 6.10
"""

import logging

import pytest
from tests.compute.ssp.supported_os.common_templates import utils
from utilities import console
from utilities.infra import Images


LOGGER = logging.getLogger(__name__)
VM_NAME = "rhel-6.10"


@pytest.mark.parametrize(
    "data_volume_scope_class, vm_object_from_template_scope_class",
    [
        (
            {
                "image": f"{Images.Rhel.DIR}/{Images.Rhel.RHEL6_IMG}",
                "dv_name": f"dv-{VM_NAME}",
            },
            {
                "vm_name": VM_NAME,
                "template_labels": {
                    "os": "rhel6.0",
                    "workload": "server",
                    "flavor": "tiny",
                },
                # A nic is not created with the default virtio nic model.
                # Need to use 1000e.
                # https://bugzilla.redhat.com/show_bug.cgi?id=1788923
                "network_model": "e1000",
                "network_multiqueue": False,
            },
        )
    ],
    indirect=True,
)
class TestCommonTemplatesRhel6:
    @pytest.mark.run("first")
    @pytest.mark.polarion("CNV-2211")
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
    @pytest.mark.polarion("CNV-3267")
    def test_start_vm(
        self,
        skip_upstream,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
    ):
        """ Test CNV common templates VM initiation """

        utils.vm_started(
            vm=vm_object_from_template_scope_class, wait_for_interfaces=False
        )

    @pytest.mark.run(after="test_start_vm")
    @pytest.mark.polarion("CNV-3260")
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
    @pytest.mark.polarion("CNV-3319")
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
    @pytest.mark.polarion("CNV-3307")
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
    @pytest.mark.polarion("CNV-3219")
    def test_expose_ssh(
        self,
        skip_upstream,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
        vm_ssh_service_scope_class,
        schedulable_node_ips,
    ):
        """ CNV common templates access VM via SSH """

        utils.enable_ssh_service_in_vm(
            vm=vm_object_from_template_scope_class,
            console_impl=console.RHEL,
            systemctl_support=False,
        )

        assert utils.check_ssh_connection(
            ip=list(schedulable_node_ips.values())[0],
            port=vm_object_from_template_scope_class.ssh_node_port,
            console_impl=console.RHEL,
        ), "Failed to login via SSH"

    @pytest.mark.run("last")
    @pytest.mark.polarion("CNV-3272")
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
