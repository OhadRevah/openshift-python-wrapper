"""
vGPU with RHEL VM
"""

import logging

import pytest
from pytest_testconfig import config as py_config

from tests.compute.utils import pause_optional_migrate_unpause_and_check_connectivity
from tests.compute.virt.gpu.utils import (
    restart_and_check_gpu_exists,
    verify_gpu_device_exists_in_vm,
    verify_gpu_device_exists_on_node,
    verify_gpu_expected_count_updated_on_node,
)
from tests.compute.virt.utils import running_sleep_in_linux
from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS, RHEL_LATEST_OS
from utilities.constants import MDEV_AVAILABLE_INSTANCES, VGPU_DEVICE_NAME


pytestmark = [
    pytest.mark.post_upgrade,
    pytest.mark.tier3,
    pytest.mark.usefixtures("skip_if_no_gpu_node", "non_existent_mdev_bus_nodes"),
]


LOGGER = logging.getLogger(__name__)
TESTS_CLASS_NAME = "TestVGPURHELGPUSSpec"


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_module, gpu_vm",
    [
        pytest.param(
            {
                "dv_name": RHEL_LATEST_OS,
                "image": RHEL_LATEST["image_path"],
                "storage_class": py_config["default_storage_class"],
                "dv_size": RHEL_LATEST["dv_size"],
            },
            {
                "vm_name": "rhel-vgpu-gpus-spec-vm",
                "template_labels": RHEL_LATEST_LABELS,
                "gpu_name": VGPU_DEVICE_NAME,
            },
        ),
    ],
    indirect=True,
)
@pytest.mark.usefixtures(
    "hco_cr_with_mdev_permitted_hostdevices",
)
class TestVGPURHELGPUSSpec:
    """
    Test vGPU with RHEL VM using GPUS Spec.
    """

    @pytest.mark.polarion("CNV-7259")
    def test_permitted_hostdevices_vgpu_visible(self, gpu_vm, gpu_nodes):
        """
        Test Permitted HostDevice is visible and count updated under Capacity/Allocatable
        section of the GPU Node.
        """
        verify_gpu_device_exists_on_node(
            gpu_nodes=gpu_nodes, device_name=VGPU_DEVICE_NAME
        )
        verify_gpu_expected_count_updated_on_node(
            gpu_nodes=gpu_nodes,
            device_name=VGPU_DEVICE_NAME,
            expected_count=MDEV_AVAILABLE_INSTANCES,
        )

    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::access_vgpus_rhel_vm")
    @pytest.mark.polarion("CNV-4761")
    def test_access_vgpus_rhel_vm(self, gpu_vm):
        """
        Test vGPU is accessible in VM with GPUs spec.
        """
        verify_gpu_device_exists_in_vm(vm=gpu_vm)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::access_vgpus_rhel_vm"])
    @pytest.mark.polarion("CNV-8080")
    def test_pause_unpause_vgpus_rhel_vm(self, gpu_vm):
        """
        Test VM with vGPU using GPUs spec, can be paused and unpaused successfully.
        """
        with running_sleep_in_linux(vm=gpu_vm):
            pause_optional_migrate_unpause_and_check_connectivity(vm=gpu_vm)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::access_vgpus_rhel_vm"])
    @pytest.mark.polarion("CNV-4767")
    def test_restart_vgpus_rhel_vm(self, gpu_vm):
        """
        Test VM with vGPU using GPUs spec, can be restarted successfully.
        """
        restart_and_check_gpu_exists(vm=gpu_vm)
