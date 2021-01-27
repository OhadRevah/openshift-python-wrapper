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
from utilities import console
from utilities.infra import Images


LOGGER = logging.getLogger(__name__)
# Negative tests require a DV, however its content is not important (VM will not be created).
FAILED_VM_IMAGE = f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}"
FAILED_VM_DV_SIZE = Images.Cirros.DEFAULT_DV_SIZE


@pytest.mark.parametrize(
    "golden_image_data_volume_multi_storage_scope_class,",
    [
        pytest.param(
            {
                "dv_name": py_config["latest_rhel_version"]["template_labels"]["os"],
                "image": py_config["latest_rhel_version"]["image_path"],
                "dv_size": py_config["latest_rhel_version"]["dv_size"],
            },
        ),
    ],
    indirect=True,
)
class TestRHELTabletDevice:
    @pytest.mark.parametrize(
        "golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function",
        [
            pytest.param(
                {
                    "vm_name": "rhel-virtio-tablet-device-vm",
                    "start_vm": True,
                    "template_labels": py_config["latest_rhel_version"][
                        "template_labels"
                    ],
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
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        golden_image_data_volume_multi_storage_scope_class,
        golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function,
    ):

        LOGGER.info("Test tablet device - virtio bus.")

        utils.check_vm_system_tablet_device(
            vm=golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function,
            console_impl=console.RHEL,
            expected_device="Virtio",
        )
        utils.check_vm_xml_tablet_device(
            vm=golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function
        )

    @pytest.mark.parametrize(
        "golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function",
        [
            pytest.param(
                {
                    "vm_name": "rhel-usb-tablet-device-vm",
                    "start_vm": True,
                    "template_labels": py_config["latest_rhel_version"][
                        "template_labels"
                    ],
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
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        golden_image_data_volume_multi_storage_scope_class,
        golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function,
    ):

        LOGGER.info("Test tablet device -  USB bus.")

        utils.check_vm_system_tablet_device(
            vm=golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function,
            console_impl=console.RHEL,
            expected_device="USB",
        )
        utils.check_vm_xml_tablet_device(
            vm=golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function
        )

    @pytest.mark.parametrize(
        "golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function",
        [
            pytest.param(
                {
                    "vm_name": "rhel-default-tablet-device-vm",
                    "start_vm": True,
                    "template_labels": py_config["latest_rhel_version"][
                        "template_labels"
                    ],
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
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        golden_image_data_volume_multi_storage_scope_class,
        golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function,
    ):

        LOGGER.info("Test tablet device - default device bus - USB.")

        utils.check_vm_system_tablet_device(
            vm=golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function,
            console_impl=console.RHEL,
            expected_device="USB",
        )
        utils.check_vm_xml_tablet_device(
            vm=golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function
        )


@pytest.mark.parametrize(
    "golden_image_data_volume_multi_storage_scope_class",
    [
        pytest.param(
            {
                "dv_name": "cirros-dv",
                "image": FAILED_VM_IMAGE,
                "dv_size": FAILED_VM_DV_SIZE,
            },
        ),
    ],
    indirect=True,
)
class TestRHELTabletDeviceNegative:
    @pytest.mark.parametrize(
        "golden_image_vm_object_from_template_multi_storage_dv_scope_class_vm_scope_function",
        [
            pytest.param(
                {
                    "vm_name": "rhel-ps2-tablet-device-vm",
                    "template_labels": py_config["latest_rhel_version"][
                        "template_labels"
                    ],
                    "vm_dict": utils.set_vm_tablet_device_dict(
                        {"name": "tablet1", "type": "tablet", "bus": "ps2"}
                    ),
                },
                marks=pytest.mark.polarion("CNV-3074"),
            ),
            pytest.param(
                {
                    "vm_name": "rhel-zen-tablet-device-vm",
                    "template_labels": py_config["latest_rhel_version"][
                        "template_labels"
                    ],
                    "vm_dict": utils.set_vm_tablet_device_dict(
                        {"name": "tablet1", "type": "tablet", "bus": "zen"}
                    ),
                },
                marks=pytest.mark.polarion("CNV-3441"),
            ),
            pytest.param(
                {
                    "vm_name": "rhel-tranition-tablet-device-vm",
                    "template_labels": py_config["latest_rhel_version"][
                        "template_labels"
                    ],
                    "vm_dict": utils.set_vm_tablet_device_dict(
                        {
                            "name": "tablet1",
                            "type": "tablet",
                            "bus": "virtio-transitional",
                        }
                    ),
                },
                marks=pytest.mark.polarion("CNV-3442"),
            ),
        ],
        indirect=True,
    )
    def test_tablet_invalid_usb_tablet_device(
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        golden_image_data_volume_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_storage_dv_scope_class_vm_scope_function,
    ):

        LOGGER.info("Test tablet device - wrong device bus.")

        with pytest.raises(UnprocessibleEntityError) as vm_exception:
            golden_image_vm_object_from_template_multi_storage_dv_scope_class_vm_scope_function.create()

            assert (
                "Input device can have only virtio or usb bus"
                in vm_exception.value.body.decode()
            ), f"VM failure with wrong reason {vm_exception}"

    @pytest.mark.parametrize(
        "golden_image_vm_object_from_template_multi_storage_dv_scope_class_vm_scope_function",
        [
            pytest.param(
                {
                    "vm_name": "rhel-keyboard-tablet-device-vm",
                    "template_labels": py_config["latest_rhel_version"][
                        "template_labels"
                    ],
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
        self,
        skip_upstream,
        unprivileged_client,
        namespace,
        golden_image_data_volume_multi_storage_scope_class,
        golden_image_vm_object_from_template_multi_storage_dv_scope_class_vm_scope_function,
    ):

        LOGGER.info("Test tablet device - wrong device type.")

        with pytest.raises(UnprocessibleEntityError) as vm_exception:
            golden_image_vm_object_from_template_multi_storage_dv_scope_class_vm_scope_function.create()

            assert (
                "Input Device Can Have Only Tablet Type"
                in vm_exception.value.body.decode()
            ), f"VM failure with wrong reason {vm_exception}"
