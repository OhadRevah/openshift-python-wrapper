# -*- coding: utf-8 -*-

"""
Common templates test Windows 12
"""

import logging

import pytest
import tests.compute.utils
from tests.compute.ssp.supported_os.common_templates import utils
from utilities.infra import BUG_STATUS_CLOSED, Images


LOGGER = logging.getLogger(__name__)
VM_NAME = "win-12"
WIN12_LICENSE_KEY = "CKWJN-48TW8-V7CVV-RQCFY-R6XCB"


@pytest.mark.parametrize(
    "data_volume_scope_class, vm_object_from_template_scope_class",
    [
        (
            {
                "image": f"{Images.Windows.DIR}/{Images.Windows.WIN12_IMG}",
                "dv_name": f"dv-{VM_NAME}",
            },
            {
                "vm_name": VM_NAME,
                "template_labels": {
                    "os": "win2k12r2",
                    "workload": "server",
                    "flavor": "medium",
                },
                "cpu_threads": 2,
            },
        )
    ],
    indirect=True,
)
class TestCommonTemplatesWin10:
    @pytest.mark.run("first")
    @pytest.mark.polarion("CNV-2228")
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
    @pytest.mark.polarion("CNV-3281")
    def test_start_vm(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
        winrmcli_pod_scope_class,
    ):
        """ Test CNV common templates VM initiation """

        tests.compute.utils.vm_started(
            vm=vm_object_from_template_scope_class, wait_for_interfaces=False
        )
        utils.wait_for_windows_vm(
            vm=vm_object_from_template_scope_class,
            version=VM_NAME.split("-")[-1],
            winrmcli_pod=winrmcli_pod_scope_class,
        )

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-1745")
    @pytest.mark.bugzilla(
        1769692, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    def test_domain_label(
        self,
        skip_upstream,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
    ):
        """ CNV common templates 'domain' label contains vm name """

        domain_label = vm_object_from_template_scope_class.body["spec"]["template"][
            "metadata"
        ]["labels"]["kubevirt.io/domain"]
        assert (
            domain_label == vm_object_from_template_scope_class.name
        ), f"Wrong domain label: {domain_label}"

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-2652")
    def test_hyperv(
        self,
        skip_upstream,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
        winrmcli_pod_scope_class,
    ):

        LOGGER.info("Verify VM HyperV values.")
        utils.check_vm_xml_hyperv(vm_object_from_template_scope_class)
        utils.check_windows_vm_hvinfo(
            vm_object_from_template_scope_class, winrmcli_pod_scope_class
        )

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-2176")
    @pytest.mark.jira("CNV-3771", run=False)
    def test_vm_license_state_after_stop_start(
        self,
        skip_upstream,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
        winrmcli_pod_scope_class,
    ):

        utils.add_activate_windows_license(
            vm_object_from_template_scope_class,
            winrmcli_pod_scope_class,
            WIN12_LICENSE_KEY,
        )

        LOGGER.info("Verify VM activation mode is not changed after VM stop/start.")
        utils.check_windows_activated_license(
            vm_object_from_template_scope_class,
            winrmcli_pod_scope_class,
            reset_action="stop_start",
        )

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3414")
    @pytest.mark.jira("CNV-3771", run=False)
    def test_vm_license_state_after_reboot(
        self,
        skip_upstream,
        namespace,
        data_volume_scope_class,
        vm_object_from_template_scope_class,
        winrmcli_pod_scope_class,
    ):

        utils.add_activate_windows_license(
            vm_object_from_template_scope_class,
            winrmcli_pod_scope_class,
            WIN12_LICENSE_KEY,
        )

        LOGGER.info("Verify VM activation mode is not changed after reboot.")
        utils.check_windows_activated_license(
            vm_object_from_template_scope_class,
            winrmcli_pod_scope_class,
            reset_action="reboot",
        )

    @pytest.mark.run("last")
    @pytest.mark.polarion("CNV-3288")
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
