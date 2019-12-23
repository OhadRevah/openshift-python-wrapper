# -*- coding: utf-8 -*-

"""
Common templates test tablet input device.
https://github.com/kubevirt/kubevirt/pull/1987
https://libvirt.org/formatdomain.html#elementsInput
"""

import logging

import pytest
from openshift.dynamic.exceptions import UnprocessibleEntityError
from pytest_testconfig import config as py_config
from tests.compute.ssp.supported_os.common_templates import utils
from tests.storage.utils import CDI_IMAGES_DIR, CIRROS_IMAGES_DIR
from utilities import console
from utilities.infra import Images


LOGGER = logging.getLogger(__name__)
# Negative tests require a DV, however its content is not important (VM will not be created).
FAILED_VM_IMAGE = f"{CDI_IMAGES_DIR}/{CIRROS_IMAGES_DIR}/{Images.Cirros.QCOW2_IMG}"


@pytest.mark.parametrize(
    "data_volume_scope_function, vm_instance_from_template_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-rhel-virtio-tablet-device-vm",
                "image": py_config.get("latest_rhel_version", {}).get("image"),
            },
            {
                "vm_name": "rhel-virtio-tablet-device-vm",
                "start_vm": True,
                "template_labels": {
                    "os": py_config.get("latest_rhel_version", {}).get("os_label"),
                    "workload": "server",
                    "flavor": "tiny",
                },
                "vm_dict": utils.set_vm_tablet_device_dict(
                    {"bus": "virtio", "name": "tablet", "type": "tablet"}
                ),
            },
            marks=pytest.mark.polarion("CNV-3072"),
        ),
    ],
    indirect=True,
)
def test_tablet_virtio_tablet_device(
    skip_upstream,
    unprivileged_client,
    namespace,
    data_volume_scope_function,
    vm_instance_from_template_scope_function,
):

    LOGGER.info("Test tablet device - virtio bus.")

    utils.check_vm_system_tablet_device(
        vm_instance_from_template_scope_function, console.RHEL, expected_device="Virtio"
    )
    utils.check_vm_xml_tablet_device(vm_instance_from_template_scope_function)


@pytest.mark.parametrize(
    "data_volume_scope_function, vm_instance_from_template_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-rhel-usb-tablet-device-vm",
                "image": py_config.get("latest_rhel_version", {}).get("image"),
            },
            {
                "vm_name": "rhel-usb-tablet-device-vm",
                "start_vm": True,
                "template_labels": {
                    "os": py_config.get("latest_rhel_version", {}).get("os_label"),
                    "workload": "server",
                    "flavor": "tiny",
                },
                "vm_dict": utils.set_vm_tablet_device_dict(
                    {"name": "my_tablet", "type": "tablet", "bus": "usb"}
                ),
            },
            marks=pytest.mark.polarion("CNV-3073"),
        ),
    ],
    indirect=True,
)
def test_tablet_usb_tablet_device(
    skip_upstream,
    unprivileged_client,
    namespace,
    data_volume_scope_function,
    vm_instance_from_template_scope_function,
):

    LOGGER.info("Test tablet device -  USB bus.")

    utils.check_vm_system_tablet_device(
        vm_instance_from_template_scope_function, console.RHEL, expected_device="USB"
    )
    utils.check_vm_xml_tablet_device(vm_instance_from_template_scope_function)


@pytest.mark.parametrize(
    "data_volume_scope_function, vm_instance_from_template_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-rhel-default-tablet-device-vm",
                "image": py_config.get("latest_rhel_version", {}).get("image"),
            },
            {
                "vm_name": "rhel-default-tablet-device-vm",
                "start_vm": True,
                "template_labels": {
                    "os": py_config.get("latest_rhel_version", {}).get("os_label"),
                    "workload": "server",
                    "flavor": "tiny",
                },
                "vm_dict": utils.set_vm_tablet_device_dict(
                    {"name": "tablet1", "type": "tablet"}
                ),
            },
            marks=pytest.mark.polarion("CNV-2640"),
        ),
    ],
    indirect=True,
)
def test_tablet_default_bus_tablet_device(
    skip_upstream,
    unprivileged_client,
    namespace,
    data_volume_scope_function,
    vm_instance_from_template_scope_function,
):

    LOGGER.info("Test tablet device - default device bus - USB.")

    utils.check_vm_system_tablet_device(
        vm_instance_from_template_scope_function, console.RHEL, expected_device="USB"
    )
    utils.check_vm_xml_tablet_device(vm_instance_from_template_scope_function)


@pytest.mark.parametrize(
    "data_volume_scope_function, vm_object_from_template_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-rhel-ps2-tablet-device-vm",
                "image": FAILED_VM_IMAGE,
                "dv_size": "1Gi",
            },
            {
                "vm_name": "rhel-ps2-tablet-device-vm",
                "template_labels": {
                    "os": py_config.get("latest_rhel_version", {}).get("os_label"),
                    "workload": "server",
                    "flavor": "tiny",
                },
                "vm_dict": utils.set_vm_tablet_device_dict(
                    {"name": "tablet1", "type": "tablet", "bus": "ps2"}
                ),
            },
            marks=pytest.mark.polarion("CNV-3074"),
        ),
        pytest.param(
            {
                "dv_name": "dv-rhel-zen-tablet-device-vm",
                "image": FAILED_VM_IMAGE,
                "dv_size": "1Gi",
            },
            {
                "vm_name": "rhel-zen-tablet-device-vm",
                "template_labels": {
                    "os": py_config.get("latest_rhel_version", {}).get("os_label"),
                    "workload": "server",
                    "flavor": "tiny",
                },
                "vm_dict": utils.set_vm_tablet_device_dict(
                    {"name": "tablet1", "type": "tablet", "bus": "zen"}
                ),
            },
            marks=pytest.mark.polarion("CNV-3441"),
        ),
        pytest.param(
            {
                "dv_name": "dv-rhel-transition-tablet-device-vm",
                "image": FAILED_VM_IMAGE,
                "dv_size": "1Gi",
            },
            {
                "vm_name": "rhel-tranition-tablet-device-vm",
                "template_labels": {
                    "os": py_config.get("latest_rhel_version", {}).get("os_label"),
                    "workload": "server",
                    "flavor": "tiny",
                },
                "vm_dict": utils.set_vm_tablet_device_dict(
                    {"name": "tablet1", "type": "tablet", "bus": "virtio-transitional"}
                ),
            },
            marks=pytest.mark.polarion("CNV-3077"),
        ),
    ],
    indirect=True,
)
def test_tablet_invalid_usb_tablet_device(
    skip_upstream,
    unprivileged_client,
    namespace,
    data_volume_scope_function,
    vm_object_from_template_scope_function,
):

    LOGGER.info("Test tablet device - wrong device bus.")

    with pytest.raises(UnprocessibleEntityError) as vm_exception:
        vm_object_from_template_scope_function.create()

        assert (
            "Input device can have only virtio or usb bus"
            in vm_exception.value.body.decode()
        ), f"VM failure with wrong reason {vm_exception}"


@pytest.mark.parametrize(
    "data_volume_scope_function, vm_object_from_template_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-rhel-keyboard-tablet-device-vm",
                "image": FAILED_VM_IMAGE,
                "dv_size": "1Gi",
            },
            {
                "vm_name": "rhel-keyboard-tablet-device-vm",
                "template_labels": {
                    "os": py_config.get("latest_rhel_version", {}).get("os_label"),
                    "workload": "server",
                    "flavor": "tiny",
                },
                "vm_dict": utils.set_vm_tablet_device_dict(
                    {"name": "tablet1", "type": "keyboard", "bus": "usb"}
                ),
            },
            marks=pytest.mark.polarion("CNV-2642"),
        ),
    ],
    indirect=True,
)
def test_tablet_invalid_type_tablet_device(
    skip_upstream,
    unprivileged_client,
    namespace,
    data_volume_scope_function,
    vm_object_from_template_scope_function,
):

    LOGGER.info("Test tablet device - wrong device type.")

    with pytest.raises(UnprocessibleEntityError) as vm_exception:
        vm_object_from_template_scope_function.create()

        assert (
            "Input Device Can Have Only Tablet Type" in vm_exception.value.body.decode()
        ), f"VM failure with wrong reason {vm_exception}"
