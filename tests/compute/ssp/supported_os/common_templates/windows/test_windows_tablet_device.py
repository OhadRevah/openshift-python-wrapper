# -*- coding: utf-8 -*-

"""
Common templates test tablet input device.
https://github.com/kubevirt/kubevirt/pull/1987
https://libvirt.org/formatdomain.html#elementsInput
"""

import logging
import re

import pytest
from pytest_testconfig import config as py_config
from tests.compute.ssp.supported_os.common_templates import utils
from utilities.infra import BUG_STATUS_CLOSED, Images
from utilities.virt import execute_winrm_cmd


pytestmark = pytest.mark.skipif(
    condition=py_config["distribution"] == "upstream",
    reason="Running only on downstream.",
)

LOGGER = logging.getLogger(__name__)
WINDOWS_DESKTOP_VERSION = [
    v for i in py_config["windows_os_matrix"] for k, v in i.items() if k == "win-10"
][0]


def check_windows_vm_tablet_device(vm, winrmcli_pod, driver_state, helper_vm=False):
    """ Verify tablet device values in Windows VMI using driverquery """

    windows_driver_query = execute_winrm_cmd(
        vmi_ip=vm.vmi.virt_launcher_pod.instance.status.podIP,
        winrmcli_pod=winrmcli_pod,
        cmd="%systemroot%\\\\system32\\\\driverquery /fo list /v",
        timeout=180,
        target_vm=vm,
        helper_vm=helper_vm,
    )

    assert re.search(
        f"Module Name:(.*)HidUsb(.*)Display Name:(.*)Microsoft "
        f"HID Class Driver(.*)Description:(.*)Microsoft HID "
        f"Class Driver(.*)Driver Type:(.*)Kernel(.*)Start "
        f"Mode:(.*)Manual(.*)State:(.*){driver_state}(.*)Status:(.*)OK",
        windows_driver_query,
        re.DOTALL,
    ), "Tablet input device (Hid) is not listed in VM drivers or is not running."


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function,"
    "vm_instance_from_template_multi_storage_scope_function,"
    "started_windows_vm",
    [
        pytest.param(
            {
                "dv_name": "dv-windows-usb-tablet-device-vm",
                "image": py_config["latest_windows_version"]["image_path"],
                "dv_size": py_config["latest_windows_version"]["dv_size"],
            },
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
            {"os_version": py_config["latest_windows_version"]["os_version"]},
            marks=pytest.mark.polarion("CNV-2644"),
        ),
    ],
    indirect=True,
)
def test_tablet_usb_tablet_device(
    unprivileged_client,
    namespace,
    data_volume_multi_storage_scope_function,
    vm_instance_from_template_multi_storage_scope_function,
    winrmcli_pod_scope_function,
    bridge_attached_helper_vm,
    started_windows_vm,
):

    LOGGER.info("Test tablet device - USB bus.")

    check_windows_vm_tablet_device(
        vm=vm_instance_from_template_multi_storage_scope_function,
        winrmcli_pod=winrmcli_pod_scope_function,
        driver_state="Running",
        helper_vm=bridge_attached_helper_vm,
    )
    utils.check_vm_xml_tablet_device(
        vm=vm_instance_from_template_multi_storage_scope_function
    )


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function,"
    "vm_instance_from_template_multi_storage_scope_function,"
    "started_windows_vm",
    [
        pytest.param(
            {
                "dv_name": "dv-windows-virtio-tablet-device-vm",
                "image": py_config["latest_windows_version"]["image_path"],
                "dv_size": py_config["latest_windows_version"]["dv_size"],
            },
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
            {"os_version": py_config["latest_windows_version"]["os_version"]},
            marks=pytest.mark.polarion("CNV-3444"),
        ),
    ],
    indirect=True,
)
def test_tablet_virtio_tablet_device(
    unprivileged_client,
    namespace,
    data_volume_multi_storage_scope_function,
    vm_instance_from_template_multi_storage_scope_function,
    winrmcli_pod_scope_function,
    bridge_attached_helper_vm,
    started_windows_vm,
):
    """Verify that when a Windows VM is configured with virtio tablet input
    device(virtio drivers do not support tablet device), the VM is running.
    """

    LOGGER.info("Test tablet device - virtio bus.")

    check_windows_vm_tablet_device(
        vm=vm_instance_from_template_multi_storage_scope_function,
        winrmcli_pod=winrmcli_pod_scope_function,
        driver_state="Stopped",
        helper_vm=bridge_attached_helper_vm,
    )

    utils.check_vm_xml_tablet_device(
        vm=vm_instance_from_template_multi_storage_scope_function
    )


@pytest.mark.bugzilla(
    1827705, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function,"
    "vm_instance_from_template_multi_storage_scope_function,"
    "started_windows_vm",
    [
        pytest.param(
            {
                "dv_name": "dv-windows-server-default-tablet",
                "image": py_config["latest_windows_version"]["image_path"],
                "dv_size": py_config["latest_windows_version"]["dv_size"],
            },
            {
                "vm_name": "windows-server-default-tablet-device",
                "template_labels": py_config["latest_windows_version"][
                    "template_labels"
                ],
                "cpu_threads": 2,
            },
            {"os_version": py_config["latest_windows_version"]["os_version"]},
            marks=pytest.mark.polarion("CNV-4151"),
        ),
    ],
    indirect=True,
)
def test_windows_server_default_tablet_device(
    unprivileged_client,
    namespace,
    data_volume_multi_storage_scope_function,
    vm_instance_from_template_multi_storage_scope_function,
    winrmcli_pod_scope_function,
    bridge_attached_helper_vm,
    started_windows_vm,
):
    """Verify that when a Windows Server VM is configured by default with
    tablet device
    """

    LOGGER.info("Test Windows Server tablet device - default table device.")

    check_windows_vm_tablet_device(
        vm=vm_instance_from_template_multi_storage_scope_function,
        winrmcli_pod=winrmcli_pod_scope_function,
        driver_state="Running",
        helper_vm=bridge_attached_helper_vm,
    )

    utils.check_vm_xml_tablet_device(
        vm=vm_instance_from_template_multi_storage_scope_function
    )


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function,"
    "vm_instance_from_template_multi_storage_scope_function,"
    "started_windows_vm",
    [
        pytest.param(
            {
                "dv_name": "dv-windows-desktop-default-tablet",
                "image": WINDOWS_DESKTOP_VERSION["image_path"],
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            },
            {
                "vm_name": "windows-desktop-default-tablet-device",
                "template_labels": {
                    "os": WINDOWS_DESKTOP_VERSION["template_labels"]["os"],
                    "workload": "desktop",
                    "flavor": "medium",
                },
                "cpu_threads": 2,
            },
            {"os_version": WINDOWS_DESKTOP_VERSION["os_version"]},
            marks=pytest.mark.polarion("CNV-4150"),
        ),
    ],
    indirect=True,
)
def test_windows_desktop_default_tablet_device(
    unprivileged_client,
    namespace,
    data_volume_multi_storage_scope_function,
    vm_instance_from_template_multi_storage_scope_function,
    winrmcli_pod_scope_function,
    bridge_attached_helper_vm,
    started_windows_vm,
):
    """Verify that when a Desktop Windows VM is configured by default with
    tablet device
    """

    LOGGER.info("Test Windows Desktop tablet device - default table device.")

    check_windows_vm_tablet_device(
        vm=vm_instance_from_template_multi_storage_scope_function,
        winrmcli_pod=winrmcli_pod_scope_function,
        driver_state="Running",
        helper_vm=bridge_attached_helper_vm,
    )

    utils.check_vm_xml_tablet_device(
        vm=vm_instance_from_template_multi_storage_scope_function
    )
