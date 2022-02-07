"""
GPU PCI Passthrough with RHEL VM
"""

import logging
import random

import pytest
from openshift.dynamic.exceptions import UnprocessibleEntityError
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
from utilities.constants import GPU_DEVICE_NAME
from utilities.virt import CIRROS_IMAGE, VirtualMachineForTests


pytestmark = [
    pytest.mark.post_upgrade,
    pytest.mark.usefixtures(
        "skip_if_no_gpu_node", "fail_if_device_unbound_to_vfiopci_driver"
    ),
]

ALLOCATABLE = "allocatable"
CAPACITY = "capacity"
TESTS_CLASS_RHEL_HOSTDEVICES_NAME = "TestPCIPassthroughRHELHostDevicesSpec"
TESTS_CLASS_RHEL_GPUS_NAME = "TestPCIPassthroughRHELGPUSSpec"
DATA_VOLUME_DICT = {
    "dv_name": RHEL_LATEST_OS,
    "image": RHEL_LATEST["image_path"],
    "storage_class": py_config["default_storage_class"],
    "dv_size": RHEL_LATEST["dv_size"],
}


LOGGER = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_module, gpu_vm",
    [
        pytest.param(
            DATA_VOLUME_DICT,
            {
                "vm_name": "rhel-passthrough-hostdevices-spec-vm",
                "template_labels": RHEL_LATEST_LABELS,
                "host_device_name": GPU_DEVICE_NAME,
            },
        ),
    ],
    indirect=True,
)
@pytest.mark.usefixtures(
    "hco_cr_with_permitted_hostdevices",
)
class TestPCIPassthroughRHELHostDevicesSpec:
    """
    Test PCI Passthrough with RHEL VM using HostDevices Spec.
    """

    @pytest.mark.polarion("CNV-5638")
    def test_permitted_hostdevices_visible(self, gpu_vm, gpu_nodes):
        """
        Test Permitted HostDevice is visible and count updated under Capacity/Allocatable
        section of the GPU Node.
        """
        verify_gpu_device_exists_on_node(
            gpu_nodes=gpu_nodes, device_name=GPU_DEVICE_NAME
        )
        verify_gpu_expected_count_updated_on_node(
            gpu_nodes=gpu_nodes,
            device_name=GPU_DEVICE_NAME,
            expected_count="1",
        )

    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_RHEL_HOSTDEVICES_NAME}::access_hostdevices_rhel_vm"
    )
    @pytest.mark.polarion("CNV-5639")
    def test_access_hostdevices_rhel_vm(self, gpu_vm):
        """
        Test Device is accessible in VM with hostdevices spec.
        """
        verify_gpu_device_exists_in_vm(vm=gpu_vm)

    @pytest.mark.dependency(
        depends=[f"{TESTS_CLASS_RHEL_HOSTDEVICES_NAME}::access_hostdevices_rhel_vm"]
    )
    @pytest.mark.polarion("CNV-5643")
    def test_pause_unpause_hostdevices_rhel_vm(self, gpu_vm):
        """
        Test VM with Device using hostdevices spec, can be paused and unpaused successfully.
        """
        with running_sleep_in_linux(vm=gpu_vm):
            pause_optional_migrate_unpause_and_check_connectivity(vm=gpu_vm)

    @pytest.mark.dependency(
        depends=[f"{TESTS_CLASS_RHEL_HOSTDEVICES_NAME}::access_hostdevices_rhel_vm"]
    )
    @pytest.mark.polarion("CNV-5641")
    def test_restart_hostdevices_rhel_vm(self, gpu_vm):
        """
        Test VM with Device using hostdevices spec, can be restarted successfully.
        """
        restart_and_check_gpu_exists(vm=gpu_vm)


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_module, gpu_vm",
    [
        pytest.param(
            DATA_VOLUME_DICT,
            {
                "vm_name": "rhel-passthrough-gpus-spec-vm",
                "template_labels": RHEL_LATEST_LABELS,
                "gpu_name": GPU_DEVICE_NAME,
            },
        ),
    ],
    indirect=True,
)
@pytest.mark.usefixtures(
    "hco_cr_with_permitted_hostdevices",
)
class TestPCIPassthroughRHELGPUSSpec:
    """
    Test PCI Passthrough with RHEL VM using GPUS Spec.
    """

    @pytest.mark.dependency(name=f"{TESTS_CLASS_RHEL_GPUS_NAME}::access_gpus_rhel_vm")
    @pytest.mark.polarion("CNV-5640")
    def test_access_gpus_rhel_vm(self, gpu_vm):
        """
        Test Device is accessible in VM with GPUS spec.
        """
        verify_gpu_device_exists_in_vm(vm=gpu_vm)

    @pytest.mark.dependency(
        depends=[f"{TESTS_CLASS_RHEL_GPUS_NAME}::access_gpus_rhel_vm"]
    )
    @pytest.mark.polarion("CNV-5644")
    def test_pause_unpause_gpus_rhel_vm(self, gpu_vm):
        """
        Test VM with Device using GPUS spec, can be paused and unpaused successfully.
        """
        with running_sleep_in_linux(vm=gpu_vm):
            pause_optional_migrate_unpause_and_check_connectivity(vm=gpu_vm)

    @pytest.mark.dependency(
        depends=[f"{TESTS_CLASS_RHEL_GPUS_NAME}::access_gpus_rhel_vm"]
    )
    @pytest.mark.polarion("CNV-5642")
    def test_restart_gpus_rhel_vm(self, gpu_vm):
        """
        Test VM with Device using GPUS spec, can be restarted successfully.
        """
        restart_and_check_gpu_exists(vm=gpu_vm)


@pytest.mark.polarion("CNV-5645")
def test_only_permitted_hostdevices_allowed(
    namespace,
    unprivileged_client,
    gpu_nodes,
):
    """Test that VM cannot be created without Permitted Hostdevices"""
    with pytest.raises(
        UnprocessibleEntityError,
        match=f"admission webhook .* denied the request: HostDevice {GPU_DEVICE_NAME} is not permitted .*",
    ):
        with VirtualMachineForTests(
            name="passthrough-non-permitted-hostdevices-vm",
            namespace=namespace.name,
            client=unprivileged_client,
            image=CIRROS_IMAGE,
            node_selector=random.choice([*gpu_nodes]).name,
            host_device_name=GPU_DEVICE_NAME,
        ):
            pytest.fail("VM should get created only with allowed Permitted Hostdevices")
