"""
GPU PCI Passthrough with RHEL VM
"""

import logging
import random

import pytest
from openshift.dynamic.exceptions import UnprocessibleEntityError
from pytest_testconfig import config as py_config

from tests.compute.virt import utils as virt_utils
from tests.compute.virt.gpu_pci_passthrough import utils as passthrough_utils
from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS, RHEL_LATEST_OS
from utilities.constants import GPU_DEVICE_NAME
from utilities.virt import (
    CIRROS_IMAGE,
    VirtualMachineForTests,
    wait_for_ssh_connectivity,
)


ALLOCATABLE = "allocatable"
CAPACITY = "capacity"

LOGGER = logging.getLogger(__name__)


def pause_unpause_and_check_connectivity(vm):
    vm.vmi.pause(wait=True)
    vm.vmi.unpause(wait=True)
    wait_for_ssh_connectivity(vm=vm)


def resources_device_checks(gpu_node, status_type):
    if status_type == ALLOCATABLE:
        resources = gpu_node.instance.status.allocatable
    elif status_type == CAPACITY:
        resources = gpu_node.instance.status.capacity

    if GPU_DEVICE_NAME not in resources.keys():
        return {
            gpu_node.name: {
                f"device_{status_type}": {
                    "expected": GPU_DEVICE_NAME,
                    "actual": resources.keys(),
                }
            }
        }
    if resources[GPU_DEVICE_NAME] != "1":
        return {
            gpu_node.name: {
                f"device_{status_type}_count": {
                    "expected": "1",
                    "actual": resources[GPU_DEVICE_NAME],
                }
            }
        }


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class, pci_passthrough_vm",
    [
        pytest.param(
            {
                "dv_name": RHEL_LATEST_OS,
                "image": RHEL_LATEST["image_path"],
                "storage_class": py_config["default_storage_class"],
                "dv_size": RHEL_LATEST["dv_size"],
            },
            {
                "vm_name": "rhel-passthrough-vm",
                "template_labels": RHEL_LATEST_LABELS,
                "host_device_name": GPU_DEVICE_NAME,
            },
        ),
    ],
    indirect=True,
)
@pytest.mark.usefixtures(
    "skip_if_no_gpu_node",
    "golden_image_data_volume_scope_class",
)
class TestPCIPassthroughRHELHostDevicesSpec:
    """
    Test PCI Passthrough with RHEL VM using HostDevices Spec.
    """

    @pytest.mark.polarion("CNV-5638")
    def test_permitted_hostdevices_visible(self, pci_passthrough_vm, gpu_nodes):
        """
        Test Permitted HostDevice is visible and count updated under Capacity/Allocatable
        section of the GPU Node.
        """
        failed_checks = []
        for gpu_node in gpu_nodes:
            for status_type in [ALLOCATABLE, CAPACITY]:
                failed_check = resources_device_checks(
                    gpu_node=gpu_node, status_type=status_type
                )
                if failed_check:
                    failed_checks.append(failed_check)
        assert not failed_checks, f"Failed checks: {failed_checks}"

    @pytest.mark.dependency(name="access_hostdevices_rhel_vm")
    @pytest.mark.polarion("CNV-5639")
    def test_access_hostdevices_rhel_vm(self, pci_passthrough_vm):
        """
        Test Device is accessible in VM with hostdevices spec.
        """
        passthrough_utils.verify_gpu_device_exists(vm=pci_passthrough_vm)

    @pytest.mark.dependency(depends=["access_hostdevices_rhel_vm"])
    @pytest.mark.polarion("CNV-5643")
    def test_pause_unpause_hostdevices_rhel_vm(self, pci_passthrough_vm):
        """
        Test VM with Device using hostdevices spec, can be paused and unpaused successfully.
        """
        with virt_utils.running_sleep_in_linux(vm=pci_passthrough_vm):
            pause_unpause_and_check_connectivity(vm=pci_passthrough_vm)

    @pytest.mark.dependency(depends=["access_hostdevices_rhel_vm"])
    @pytest.mark.polarion("CNV-5641")
    def test_restart_hostdevices_rhel_vm(self, pci_passthrough_vm):
        """
        Test VM with Device using hostdevices spec, can be restarted successfully.
        """
        passthrough_utils.restart_and_check_device_exists(vm=pci_passthrough_vm)

    @pytest.mark.dependency(name="access_gpus_rhel_vm")
    @pytest.mark.polarion("CNV-5640")
    def test_access_gpus_rhel_vm(self, pci_passthrough_vm, updated_vm_gpus_spec):
        """
        Test Device is accessible in VM with GPUs spec.
        """
        passthrough_utils.restart_and_check_device_exists(vm=pci_passthrough_vm)

    @pytest.mark.dependency(depends=["access_gpus_rhel_vm"])
    @pytest.mark.polarion("CNV-5644")
    def test_pause_unpause_gpus_rhel_vm(self, pci_passthrough_vm):
        """
        Test VM with Device using GPUs spec, can be paused and unpaused successfully.
        """
        with virt_utils.running_sleep_in_linux(vm=pci_passthrough_vm):
            pause_unpause_and_check_connectivity(vm=pci_passthrough_vm)

    @pytest.mark.dependency(depends=["access_gpus_rhel_vm"])
    @pytest.mark.polarion("CNV-5642")
    def test_restart_gpus_rhel_vm(self, pci_passthrough_vm):
        """
        Test VM with Device using GPUs spec, can be restarted successfully.
        """
        passthrough_utils.restart_and_check_device_exists(vm=pci_passthrough_vm)


@pytest.mark.polarion("CNV-5645")
def test_only_permitted_hostdevices_allowed(
    skip_if_no_gpu_node,
    namespace,
    unprivileged_client,
    gpu_nodes,
):
    """Test that VM cannot be created without Permitted Hostdevices"""
    gpu_device_name = "nvidia.com/Tesla_A100"
    with pytest.raises(
        UnprocessibleEntityError,
        match=f"admission webhook .* denied the request: HostDevice {gpu_device_name} is not permitted .*",
    ):
        with VirtualMachineForTests(
            name="passthrough-non-permitted-hostdevices-vm",
            namespace=namespace.name,
            client=unprivileged_client,
            image=CIRROS_IMAGE,
            node_selector=random.choice(gpu_nodes).name,
            host_device_name=gpu_device_name,
        ):
            pytest.fail("VM should get created only with allowed Permitted Hostdevices")
