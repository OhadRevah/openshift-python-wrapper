"""
vGPU with Windows VM
"""

import logging
import os

import pytest
from pytest_testconfig import config as py_config

from tests.compute.utils import validate_pause_optional_migrate_unpause_windows_vm
from tests.compute.virt.gpu.utils import (
    restart_and_check_gpu_exists,
    verify_gpu_device_exists_in_vm,
)
from utilities.constants import VGPU_DEVICE_NAME, Images
from utilities.virt import get_windows_os_dict


pytestmark = [
    pytest.mark.post_upgrade,
    pytest.mark.tier3,
    pytest.mark.usefixtures("skip_if_no_gpu_node", "non_existent_mdev_bus_nodes"),
]


LOGGER = logging.getLogger(__name__)
WIN10 = get_windows_os_dict(windows_version="win-10")
WIN10_LABELS = WIN10["template_labels"]
DV_SIZE = Images.Windows.NVIDIA_DV_SIZE
TESTS_CLASS_NAME = "TestVGPUWindowsGPUSSpec"


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_module, gpu_vm",
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
                "vm_name": "win10-vgpu-gpus-spec-vm",
                "template_labels": WIN10_LABELS,
                "gpu_name": VGPU_DEVICE_NAME,
                "cloned_dv_size": DV_SIZE,
            },
            id="test_win10_vgpu",
        ),
    ],
    indirect=True,
)
@pytest.mark.usefixtures(
    "hco_cr_with_mdev_permitted_hostdevices",
)
class TestVGPUWindowsGPUSSpec:
    """
    Test vGPU with Windows VM using gpus spec.
    """

    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::access_gpus_win_vm")
    @pytest.mark.polarion("CNV-8081")
    def test_access_gpus_win_vm(self, gpu_vm):
        """
        Test vGPU is accessible in Windows VM with gpus spec.
        """
        verify_gpu_device_exists_in_vm(vm=gpu_vm)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::access_gpus_win_vm"])
    @pytest.mark.polarion("CNV-8082")
    def test_pause_unpause_gpus_win_vm(self, gpu_vm):
        """
        Test Windows VM with vGPU using gpus spec, can be paused and unpaused successfully.
        """
        validate_pause_optional_migrate_unpause_windows_vm(vm=gpu_vm)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::access_gpus_win_vm"])
    @pytest.mark.polarion("CNV-8083")
    def test_restart_gpus_win_vm(self, gpu_vm):
        """
        Test Windows VM with vGPU using gpus spec, can be restarted successfully.
        """
        restart_and_check_gpu_exists(vm=gpu_vm)