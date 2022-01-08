"""
GPU PCI Passthrough with Windows VM
"""

import logging
import os

import pytest
from pytest_testconfig import config as py_config

from tests.compute import utils as compute_utils
from tests.compute.virt.gpu_pci_passthrough import utils as passthrough_utils
from utilities.constants import GPU_DEVICE_NAME, Images
from utilities.virt import get_windows_os_dict


pytestmark = [
    pytest.mark.post_upgrade,
    pytest.mark.usefixtures(
        "skip_if_no_gpu_node", "fail_if_device_unbound_to_vfiopci_driver"
    ),
]


LOGGER = logging.getLogger(__name__)
WIN10 = get_windows_os_dict(windows_version="win-10")
WIN10_LABELS = WIN10["template_labels"]
WIN19 = get_windows_os_dict(windows_version="win-19")
WIN19_LABELS = WIN19["template_labels"]
DV_SIZE = Images.Windows.NVIDIA_DV_SIZE
TESTS_CLASS_NAME = "TestPCIPassthroughWinHostDevicesSpec"


@pytest.mark.tier3
@pytest.mark.parametrize(
    "golden_image_data_volume_scope_module, pci_passthrough_vm",
    [
        pytest.param(
            {
                "dv_name": WIN10_LABELS["os"],
                "image": os.path.join(
                    Images.Windows.DIR, Images.Windows.WIM10_NVIDIA_IMG
                ),
                "storage_class": py_config["default_storage_class"],
                "dv_size": DV_SIZE,
            },
            {
                "vm_name": "win10-passthrough-vm",
                "template_labels": WIN10_LABELS,
                "host_device_name": GPU_DEVICE_NAME,
                "cloned_dv_size": DV_SIZE,
            },
            id="test_win10_pci_passthrough",
        ),
        pytest.param(
            {
                "dv_name": WIN19_LABELS["os"],
                "image": os.path.join(
                    Images.Windows.DIR, Images.Windows.WIN19_NVIDIA_IMG
                ),
                "storage_class": py_config["default_storage_class"],
                "dv_size": DV_SIZE,
            },
            {
                "vm_name": "win19-passthrough-vm",
                "template_labels": WIN19_LABELS,
                "host_device_name": GPU_DEVICE_NAME,
                "cloned_dv_size": DV_SIZE,
            },
            id="test_win19_pci_passthrough",
        ),
    ],
    indirect=True,
)
@pytest.mark.usefixtures(
    "hco_cr_with_permitted_hostdevices",
)
class TestPCIPassthroughWinHostDevicesSpec:
    """
    Test PCI Passthrough with Windows VM using HostDevices Spec.
    """

    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::access_hostdevices_win_vm")
    @pytest.mark.polarion("CNV-5646")
    def test_access_hostdevices_win_vm(self, pci_passthrough_vm):
        """
        Test Device is accessible in Windows VM with hostdevices spec.
        """
        passthrough_utils.verify_gpu_device_exists(vm=pci_passthrough_vm)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::access_hostdevices_win_vm"])
    @pytest.mark.polarion("CNV-5647")
    def test_pause_unpause_hostdevices_win_vm(self, pci_passthrough_vm):
        """
        Test Windows VM with Device using hostdevices spec, can be paused and unpaused successfully.
        """
        compute_utils.validate_pause_optional_migrate_unpause_windows_vm(
            vm=pci_passthrough_vm
        )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::access_hostdevices_win_vm"])
    @pytest.mark.polarion("CNV-5648")
    def test_restart_hostdevices_win_vm(self, pci_passthrough_vm):
        """
        Test Windows VM with Device using hostdevices spec, can be restarted successfully.
        """
        passthrough_utils.restart_and_check_device_exists(vm=pci_passthrough_vm)

    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::access_gpus_win_vm")
    @pytest.mark.polarion("CNV-5742")
    def test_access_gpus_win_vm(self, pci_passthrough_vm, updated_vm_gpus_spec):
        """
        Test Device is accessible in Windows VM with gpus spec.
        """
        passthrough_utils.restart_and_check_device_exists(vm=pci_passthrough_vm)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::access_gpus_win_vm"])
    @pytest.mark.polarion("CNV-5743")
    def test_pause_unpause_gpus_win_vm(self, pci_passthrough_vm):
        """
        Test Windows VM with Device using gpus spec, can be paused and unpaused successfully.
        """
        compute_utils.validate_pause_optional_migrate_unpause_windows_vm(
            vm=pci_passthrough_vm
        )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::access_gpus_win_vm"])
    @pytest.mark.polarion("CNV-5744")
    def test_restart_gpus_win_vm(self, pci_passthrough_vm):
        """
        Test Windows VM with Device using gpus spec, can be restarted successfully.
        """
        passthrough_utils.restart_and_check_device_exists(vm=pci_passthrough_vm)
