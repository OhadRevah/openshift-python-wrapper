# -*- coding: utf-8 -*-

"""
Common templates test tablet input device.
https://github.com/kubevirt/kubevirt/pull/1987
https://libvirt.org/formatdomain.html#elementsInput
"""

import logging
import re
import shlex

import pytest
from pytest_testconfig import config as py_config

from tests.compute.ssp.supported_os.common_templates import utils
from utilities.virt import get_windows_os_dict


pytestmark = pytest.mark.skipif(
    condition=py_config["distribution"] == "upstream",
    reason="Running only on downstream.",
)

LOGGER = logging.getLogger(__name__)
WINDOWS_DESKTOP_VERSION = get_windows_os_dict(windows_version="win-10")


def check_windows_vm_tablet_device(vm, driver_state):
    """ Verify tablet device values in Windows VMI using driverquery """

    windows_driver_query = vm.ssh_exec.run_command(
        command=shlex.split("%systemroot%\\\\system32\\\\driverquery /fo list /v"),
    )[1]

    assert re.search(
        f"Module Name:(.*)HidUsb(.*)Display Name:(.*)Microsoft "
        f"HID Class Driver(.*)Description:(.*)Microsoft HID "
        f"Class Driver(.*)Driver Type:(.*)Kernel(.*)Start "
        f"Mode:(.*)Manual(.*)State:(.*){driver_state}(.*)Status:(.*)OK",
        windows_driver_query,
        re.DOTALL,
    ), "Tablet input device (Hid) is not listed in VM drivers or is not running."


@pytest.mark.parametrize(
    "golden_image_data_volume_multi_storage_scope_class",
    [
        pytest.param(
            {
                "dv_name": py_config["latest_windows_version"]["template_labels"]["os"],
                "image": py_config["latest_windows_version"]["image_path"],
                "dv_size": py_config["latest_windows_version"]["dv_size"],
            },
        ),
    ],
    indirect=True,
)
class TestWindowsTabletDevice:
    @pytest.mark.parametrize(
        "golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function",
        [
            pytest.param(
                {
                    "vm_name": "windows-usb-tablet-device-vm",
                    "template_labels": py_config["latest_windows_version"][
                        "template_labels"
                    ],
                    "cpu_threads": 2,
                    "vm_dict": utils.set_vm_tablet_device_dict(
                        {"name": "tablet1", "type": "tablet", "bus": "usb"}
                    ),
                },
                marks=pytest.mark.polarion("CNV-2644"),
            ),
        ],
        indirect=True,
    )
    def test_tablet_usb_tablet_device(
        self,
        unprivileged_client,
        namespace,
        golden_image_data_volume_multi_storage_scope_class,
        golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function,
    ):

        LOGGER.info("Test tablet device - USB bus.")

        check_windows_vm_tablet_device(
            vm=golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function,
            driver_state="Running",
        )
        utils.check_vm_xml_tablet_device(
            vm=golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function
        )

    @pytest.mark.parametrize(
        "golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function",
        [
            pytest.param(
                {
                    "vm_name": "windows-virtio-tablet-device-vm",
                    "template_labels": py_config["latest_windows_version"][
                        "template_labels"
                    ],
                    "cpu_threads": 2,
                    "vm_dict": utils.set_vm_tablet_device_dict(
                        {"name": "win_tablet", "type": "tablet", "bus": "virtio"}
                    ),
                },
                marks=pytest.mark.polarion("CNV-3444"),
            ),
        ],
        indirect=True,
    )
    def test_tablet_virtio_tablet_device(
        self,
        unprivileged_client,
        namespace,
        golden_image_data_volume_multi_storage_scope_class,
        golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function,
    ):
        """Verify that when a Windows VM is configured with virtio tablet input
        device(virtio drivers do not support tablet device), the VM is running.
        """

        LOGGER.info("Test tablet device - virtio bus.")

        check_windows_vm_tablet_device(
            vm=golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function,
            driver_state="Stopped",
        )

        utils.check_vm_xml_tablet_device(
            vm=golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function
        )

    @pytest.mark.parametrize(
        "golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function",
        [
            pytest.param(
                {
                    "vm_name": "windows-server-default-tablet-device",
                    "template_labels": py_config["latest_windows_version"][
                        "template_labels"
                    ],
                    "cpu_threads": 2,
                },
                marks=pytest.mark.polarion("CNV-4151"),
            ),
        ],
        indirect=True,
    )
    def test_windows_server_default_tablet_device(
        self,
        unprivileged_client,
        namespace,
        golden_image_data_volume_multi_storage_scope_class,
        golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function,
    ):
        """Verify that when a Windows Server VM is configured by default with
        tablet device
        """

        LOGGER.info("Test Windows Server tablet device - default table device.")

        check_windows_vm_tablet_device(
            vm=golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function,
            driver_state="Running",
        )

        utils.check_vm_xml_tablet_device(
            vm=golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function
        )


@pytest.mark.parametrize(
    "golden_image_data_volume_multi_storage_scope_function,"
    "golden_image_vm_instance_from_template_multi_storage_scope_function,",
    [
        pytest.param(
            {
                "dv_name": WINDOWS_DESKTOP_VERSION["template_labels"]["os"],
                "image": WINDOWS_DESKTOP_VERSION["image_path"],
                "dv_size": WINDOWS_DESKTOP_VERSION["dv_size"],
            },
            {
                "vm_name": "windows-desktop-default-tablet-device",
                "template_labels": WINDOWS_DESKTOP_VERSION["template_labels"],
                "cpu_threads": 2,
            },
            marks=pytest.mark.polarion("CNV-4150"),
        ),
    ],
    indirect=True,
)
def test_windows_desktop_default_tablet_device(
    unprivileged_client,
    namespace,
    golden_image_data_volume_multi_storage_scope_function,
    golden_image_vm_instance_from_template_multi_storage_scope_function,
):
    """Verify that when a Desktop Windows VM is configured by default with
    tablet device
    """

    LOGGER.info("Test Windows Desktop tablet device - default table device.")

    check_windows_vm_tablet_device(
        vm=golden_image_vm_instance_from_template_multi_storage_scope_function,
        driver_state="Running",
    )

    utils.check_vm_xml_tablet_device(
        vm=golden_image_vm_instance_from_template_multi_storage_scope_function
    )
