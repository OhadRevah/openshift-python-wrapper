# -*- coding: utf-8 -*-

"""
Common templates test RHEL 8.0
"""

import logging

import pytest
from pytest_testconfig import config as py_config
from tests.compute.ssp.supported_os.common_templates import utils
from utilities import console
from utilities.infra import Images


LOGGER = logging.getLogger(__name__)
VM_NAME = "rhel-8-0"


@pytest.mark.skipif(
    py_config["distribution"] == "upstream",
    reason="Running only on downstream,"
    "Reason: http_server is not available for upstream",
)
@pytest.mark.parametrize(
    "data_volume_scope_class, vm_object_from_template",
    [
        (
            {"image": Images.Rhel.RHEL8_0_IMG, "dv_name": f"dv-{VM_NAME}"},
            {
                "vm_name": VM_NAME,
                "template_labels": {
                    "os": "rhel8.0",
                    "workload": "server",
                    "flavor": "tiny",
                },
            },
        )
    ],
    indirect=True,
)
class TestCommonTemplatesRhel8:
    @pytest.mark.run("first")
    @pytest.mark.polarion("CNV-2174")
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
    @pytest.mark.polarion("CNV-3265")
    def test_start_vm(
        self, namespace, data_volume_scope_class, vm_object_from_template
    ):
        """ Test CNV common templates VM initiation """

        utils.vm_started(vm=vm_object_from_template)

    @pytest.mark.run(after="test_start_vm")
    @pytest.mark.polarion("CNV-3258")
    def test_vm_console(
        self, namespace, data_volume_scope_class, vm_object_from_template
    ):
        """ Test CNV common templates VM console """

        LOGGER.info("Verify VM console connection.")
        console.RHEL(vm=vm_object_from_template, timeout=1500)

    @pytest.mark.run(after="test_vm_console")
    @pytest.mark.polarion("CNV-3317")
    def test_os_version(
        self, namespace, data_volume_scope_class, vm_object_from_template
    ):
        """ Test CNV common templates OS version """

        utils.vm_os_version(vm=vm_object_from_template)

    @pytest.mark.run("last")
    @pytest.mark.polarion("CNV-3271")
    def test_vm_deletion(
        self, namespace, data_volume_scope_class, vm_object_from_template
    ):
        """ Test CNV common templates VM deletion """

        if not utils.vm_deleted(vm=vm_object_from_template):
            pytest.xfail("VM was not created, nothing to delete.")
