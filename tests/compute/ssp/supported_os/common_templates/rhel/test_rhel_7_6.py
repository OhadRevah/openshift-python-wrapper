# -*- coding: utf-8 -*-

"""
Common templates test RHEL 7.6
"""

import logging

import pytest
from tests.compute.ssp.supported_os.common_templates import utils
from utilities import console
from utilities.infra import Images


LOGGER = logging.getLogger(__name__)
VM_NAME = "rhel-7.6"


@pytest.mark.parametrize(
    "data_volume_scope_class, vm_object_from_template",
    [
        (
            {"image": Images.Rhel.RHEL7_6_IMG, "dv_name": f"dv-{VM_NAME}"},
            {
                "vm_name": VM_NAME,
                "template_labels": {
                    "os": "rhel7.0",
                    "workload": "server",
                    "flavor": "tiny",
                },
            },
        )
    ],
    indirect=True,
)
@pytest.mark.usefixtures("skip_upstream")
class TestCommonTemplatesRhel76:
    @pytest.mark.run("first")
    @pytest.mark.polarion("CNV-2210")
    def test_create_vm(
        self,
        unprivileged_client,
        namespace,
        data_volume_scope_class,
        vm_object_from_template,
    ):
        """ Test CNV VM creation from template """

        LOGGER.info("Create VM from template.")
        vm_object_from_template.create(wait=True)

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3266")
    def test_start_vm(
        self, namespace, data_volume_scope_class, vm_object_from_template
    ):
        """ Test CNV common templates VM initiation """

        utils.vm_started(vm=vm_object_from_template)

    @pytest.mark.run(after="test_start_vm")
    @pytest.mark.polarion("CNV-3259")
    def test_vm_console(
        self, namespace, data_volume_scope_class, vm_object_from_template
    ):
        """ Test CNV common templates VM console """

        LOGGER.info("Verify VM console connection.")
        with console.RHEL(vm=vm_object_from_template, timeout=1500):
            pass

    @pytest.mark.run(after="test_vm_console")
    @pytest.mark.polarion("CNV-3318")
    def test_os_version(
        self, namespace, data_volume_scope_class, vm_object_from_template
    ):
        """ Test CNV common templates OS version """

        utils.vm_os_version(vm=vm_object_from_template, console_impl=console.RHEL)

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3306")
    def test_domain_label(
        self, namespace, data_volume_scope_class, vm_object_from_template
    ):
        """ CNV common templates 'domain' label contains vm name """

        domain_label = vm_object_from_template.instance.spec.template.metadata[
            "labels"
        ]["kubevirt.io/domain"]
        assert (
            domain_label == vm_object_from_template.name
        ), f"Wrong domain label: {domain_label}"

    @pytest.mark.run(after="test_start_vm")
    @pytest.mark.polarion("CNV-3320")
    @pytest.mark.parametrize(
        "enabled_ssh_service_in_vm", [{"console_impl": console.RHEL}], indirect=True
    )
    def test_expose_ssh(
        self,
        namespace,
        data_volume_scope_class,
        vm_object_from_template,
        enabled_ssh_service_in_vm,
        vm_ssh_service,
        schedulable_node_ips,
    ):
        """ CNV common templates access VM via SSH """

        assert utils.check_ssh_connection(
            ip=list(schedulable_node_ips.values())[0],
            port=vm_object_from_template.ssh_node_port,
            console_impl=console.RHEL,
        ), "Failed to login via SSH"

    @pytest.mark.run("last")
    @pytest.mark.polarion("CNV-3269")
    def test_vm_deletion(
        self, namespace, data_volume_scope_class, vm_object_from_template
    ):
        """ Test CNV common templates VM deletion """

        if not utils.vm_deleted(vm=vm_object_from_template):
            pytest.xfail("VM was not created, nothing to delete.")
