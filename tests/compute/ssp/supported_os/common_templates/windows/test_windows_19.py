# -*- coding: utf-8 -*-

"""
Common templates test Windows 19
"""

import logging

import pytest
from pytest_testconfig import config as py_config
from tests.compute.ssp.supported_os.common_templates import utils
from utilities.infra import BUG_STATUS_CLOSED, Images


LOGGER = logging.getLogger(__name__)
VM_NAME = "win-19"


@pytest.mark.skipif(
    not py_config["bare_metal_cluster"],
    reason="Running only BM, Reason: windows run slow on nested visualization",
)
@pytest.mark.skipif(
    py_config["distribution"] == "upstream",
    reason="Running only on downstream,"
    "Reason: http_server is not available for upstream",
)
@pytest.mark.parametrize(
    "data_volume_scope_class, vm_object_from_template",
    [
        (
            {
                "image": Images.Windows.WIN19_IMG,
                "dv_name": f"dv-{VM_NAME}",
                "dv_size": "25Gi",
            },
            {
                "vm_name": VM_NAME,
                "template_labels": {
                    "os": "win2k19",
                    "workload": "desktop",
                    "flavor": "medium",
                },
            },
        )
    ],
    indirect=True,
)
class TestCommonTemplatesWin10:
    @pytest.mark.run("first")
    @pytest.mark.polarion("CNV-2816")
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
    @pytest.mark.polarion("CNV-3268")
    def test_start_vm(
        self,
        unprivileged_client,
        namespace,
        data_volume_scope_class,
        vm_object_from_template,
        winrmcli_pod_scope_class,
    ):
        """ Test CNV common templates VM initiation """

        utils.vm_started(vm=vm_object_from_template, wait_for_interfaces=False)
        utils.wait_for_windows_vm(
            vm=vm_object_from_template,
            version=VM_NAME.split("-")[-1],
            winrmcli_pod=winrmcli_pod_scope_class,
        )

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3301")
    @pytest.mark.bugzilla(
        1769692, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    def test_domain_label(
        self, namespace, data_volume_scope_class, vm_object_from_template
    ):
        """ CNV common templates 'domain' label contains vm name """

        domain_label = vm_object_from_template.body["spec"]["template"]["metadata"][
            "labels"
        ]["kubevirt.io/domain"]
        assert (
            domain_label == vm_object_from_template.name
        ), f"Wrong domain label: {domain_label}"

    @pytest.mark.run("last")
    @pytest.mark.polarion("CNV-3291")
    def test_vm_deletion(
        self, namespace, data_volume_scope_class, vm_object_from_template
    ):
        """ Test CNV common templates VM deletion """

        if not utils.vm_deleted(vm=vm_object_from_template):
            pytest.xfail("VM was not created, nothing to delete.")
