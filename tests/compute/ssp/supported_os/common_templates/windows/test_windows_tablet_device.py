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
from tests.compute.utils import execute_winrm_cmd


LOGGER = logging.getLogger(__name__)


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
    ), ("Tablet input device (Hid) is not listed in VM drivers or is " "not running.")


@pytest.mark.parametrize(
    "data_volume_scope_function, vm_instance_from_template_scope_function, started_windows_vm",
    [
        pytest.param(
            {
                "dv_name": "dv-windows-usb-tablet-device-vm",
                "image": py_config.get("latest_windows_version", {}).get("image"),
            },
            {
                "vm_name": "windows-usb-tablet-device-vm",
                "start_vm": True,
                "guest_agent": False,
                "template_labels": {
                    "os": py_config.get("latest_windows_version", {}).get("os_label"),
                    "workload": "server",
                    "flavor": "medium",
                },
                "cpu_threads": 2,
                "vm_dict": utils.set_vm_tablet_device_dict(
                    {"name": "tablet1", "type": "tablet", "bus": "usb"}
                ),
            },
            {
                "os_version": py_config.get("latest_windows_version", {}).get(
                    "os_label"
                )[-2:],
            },
            marks=pytest.mark.polarion("CNV-2644"),
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
    winrmcli_pod_scope_function,
    bridge_attached_helper_vm,
    started_windows_vm,
):

    LOGGER.info("Test tablet device - USB bus.")

    check_windows_vm_tablet_device(
        vm=vm_instance_from_template_scope_function,
        winrmcli_pod=winrmcli_pod_scope_function,
        driver_state="Running",
        helper_vm=bridge_attached_helper_vm,
    )
    utils.check_vm_xml_tablet_device(vm_instance_from_template_scope_function)


@pytest.mark.parametrize(
    "data_volume_scope_function, vm_instance_from_template_scope_function, started_windows_vm",
    [
        pytest.param(
            {
                "dv_name": "dv-windows-virtio-tablet-device-vm",
                "image": py_config.get("latest_windows_version", {}).get("image"),
            },
            {
                "vm_name": "windows-virtio-tablet-device-vm",
                "template_labels": {
                    "os": py_config.get("latest_windows_version", {}).get("os_label"),
                    "workload": "server",
                    "flavor": "medium",
                },
                "cpu_threads": 2,
                "start_vm": True,
                "guest_agent": False,
                "vm_dict": utils.set_vm_tablet_device_dict(
                    {"name": "win_tablet", "type": "tablet", "bus": "virtio"}
                ),
            },
            {
                "os_version": py_config.get("latest_windows_version", {}).get(
                    "os_label"
                )[-2:],
            },
            marks=pytest.mark.polarion("CNV-3444"),
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
    winrmcli_pod_scope_function,
    bridge_attached_helper_vm,
    started_windows_vm,
):
    """ Verify that when a Windows VM is configured with virtio tablet input
    device(virtio drivers do not support tablet device), the VM is running.
    """

    LOGGER.info("Test tablet device - virtio bus.")

    check_windows_vm_tablet_device(
        vm=vm_instance_from_template_scope_function,
        winrmcli_pod=winrmcli_pod_scope_function,
        driver_state="Stopped",
        helper_vm=bridge_attached_helper_vm,
    )

    utils.check_vm_xml_tablet_device(vm_instance_from_template_scope_function)
