# -*- coding: utf-8 -*-

"""
Common templates test latest Fedora
"""

import logging

import pytest
from pytest_testconfig import config as py_config
from tests.compute.ssp.supported_os.common_templates import utils
from utilities import console
from utilities.infra import BUG_STATUS_CLOSED


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
                "dv_name": f'dv-{py_config["common_templates_latest_fedora_version"]["os_label"]}',
                "image": py_config["common_templates_latest_fedora_version"]["image"],
            },
            {
                "vm_name": py_config["common_templates_latest_fedora_version"][
                    "os_label"
                ],
                "template_labels": {
                    "os": py_config["common_templates_latest_fedora_version"][
                        "os_label"
                    ],
                    "workload": "desktop",
                    "flavor": "tiny",
                },
                "vm_dict": HYPERV_DICT,
            },
        )
    ],
    indirect=True,
)
class TestCommonTemplatesFedora:
    @pytest.mark.run("first")
    @pytest.mark.polarion("CNV-3351")
    def test_create_vm(
        self,
        unprivileged_client,
        namespace,
        data_volume_scope_class,
        vm_object_from_template,
    ):
        """ Test CNV VM creation from template """

        LOGGER.info(
            'Create VM from template - {py_config["common_templates_latest_fedora_version"]["os_label"]}'
        )
        vm_object_from_template.create(wait=True)

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3345")
    def test_start_vm(
        self, namespace, data_volume_scope_class, vm_object_from_template
    ):
        """ Test CNV common templates VM initiation """

        utils.vm_started(vm=vm_object_from_template, wait_for_interfaces=False)

    @pytest.mark.run("test_start_vm")
    @pytest.mark.polarion("CNV-2651")
    def test_vm_hyperv(
        self, namespace, data_volume_scope_class, vm_object_from_template,
    ):
        LOGGER.info("Verify VMI HyperV values.")
        utils.check_vm_xml_hyperv(vm_object_from_template)

    @pytest.mark.run(after="test_start_vm")
    @pytest.mark.polarion("CNV-3344")
    def test_vm_console(
        self, namespace, data_volume_scope_class, vm_object_from_template
    ):
        """ Test CNV common templates VM console """

        LOGGER.info("Verify VM console connection.")
        with console.Fedora(vm=vm_object_from_template, timeout=1500):
            pass

    @pytest.mark.run(after="test_vm_console")
    @pytest.mark.polarion("CNV-3348")
    @pytest.mark.bugzilla(
        1766069, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    def test_os_version(
        self, namespace, data_volume_scope_class, vm_object_from_template
    ):
        """ Test CNV common templates OS version """

        utils.vm_os_version(vm=vm_object_from_template)

    @pytest.mark.run(after="test_create_vm")
    @pytest.mark.polarion("CNV-3347")
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
    @pytest.mark.polarion("CNV-3349")
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
        ), "Failed to login via SSH"

    @pytest.mark.run("last")
    @pytest.mark.polarion("CNV-3346")
    def test_vm_deletion(
        self, namespace, data_volume_scope_class, vm_object_from_template
    ):
        """ Test CNV common templates VM deletion """

        if not utils.vm_deleted(vm=vm_object_from_template):
            pytest.xfail("VM was not created, nothing to delete.")
