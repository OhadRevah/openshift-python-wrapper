"""
vGPU with RHEL VM
"""
import logging

import pytest
from ocp_resources.template import Template
from pytest_testconfig import config as py_config

from tests.compute.utils import pause_optional_migrate_unpause_and_check_connectivity
from tests.compute.virt.gpu.utils import (
    get_num_gpu_devices_in_rhel_vm,
    restart_and_check_gpu_exists,
    verify_gpu_device_exists_in_vm,
    verify_gpu_device_exists_on_node,
    verify_gpu_expected_count_updated_on_node,
)
from tests.compute.virt.utils import running_sleep_in_linux
from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS, RHEL_LATEST_OS
from utilities.constants import (
    MDEV_AVAILABLE_INSTANCES,
    MDEV_GRID_T4_16Q_AVAILABLE_INSTANCES,
    VGPU_DEVICE_NAME,
    VGPU_GRID_T4_16Q_NAME,
)
from utilities.virt import (
    VirtualMachineForTestsFromTemplate,
    running_vm,
    vm_instance_from_template,
)


pytestmark = [
    pytest.mark.post_upgrade,
    pytest.mark.tier3,
    pytest.mark.usefixtures("skip_if_no_gpu_node", "non_existent_mdev_bus_nodes"),
]


LOGGER = logging.getLogger(__name__)
TESTS_CLASS_NAME = "TestVGPURHELGPUSSpec"


@pytest.fixture(scope="class")
def gpu_vmb(
    unprivileged_client,
    namespace,
    golden_image_dv_scope_module_data_source_scope_class,
    gpu_nodes,
    gpu_vma,
):
    """
    VM Fixture for second VM for vGPU based Tests.
    """
    with VirtualMachineForTestsFromTemplate(
        name="rhel-vgpu-gpus-spec-vm2",
        namespace=namespace.name,
        client=unprivileged_client,
        labels=Template.generate_template_labels(**RHEL_LATEST_LABELS),
        data_source=golden_image_dv_scope_module_data_source_scope_class,
        node_selector=gpu_vma.node_selector,
        gpu_name=VGPU_DEVICE_NAME,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def node_mdevtype_gpu_vm(
    request,
    unprivileged_client,
    namespace,
    golden_image_dv_scope_module_data_source_scope_class,
    gpu_nodes,
):
    """
    VM Fixture for nodeMediatedDeviceType vGPU based Tests.

    This VM fixture is used to create a VM on a node on which
    the global GPU Mdev Type has been overridden via the configuration
    'nodeMediatedDeviceTypes' in HCO CR.
    """
    with vm_instance_from_template(
        request=request,
        namespace=namespace,
        unprivileged_client=unprivileged_client,
        data_source=golden_image_dv_scope_module_data_source_scope_class,
        node_selector=[*gpu_nodes][1].name,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def vm_with_no_gpu(gpu_vma, node_mdevtype_gpu_vm):
    return [
        vm.name
        for vm in [gpu_vma, node_mdevtype_gpu_vm]
        if not get_num_gpu_devices_in_rhel_vm(vm=vm) == 1
    ]


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_module, gpu_vma",
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
    def test_permitted_hostdevices_vgpu_visible(self, gpu_vma, gpu_nodes):
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

    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::test_access_vgpus_rhel_vm")
    @pytest.mark.polarion("CNV-4761")
    def test_access_vgpus_rhel_vm(self, gpu_vma):
        """
        Test vGPU is accessible in VM with GPUs spec.
        """
        verify_gpu_device_exists_in_vm(vm=gpu_vma)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::test_access_vgpus_rhel_vm"])
    @pytest.mark.polarion("CNV-8080")
    def test_pause_unpause_vgpus_rhel_vm(self, gpu_vma):
        """
        Test VM with vGPU using GPUs spec, can be paused and unpaused successfully.
        """
        with running_sleep_in_linux(vm=gpu_vma):
            pause_optional_migrate_unpause_and_check_connectivity(vm=gpu_vma)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::test_access_vgpus_rhel_vm"])
    @pytest.mark.polarion("CNV-4767")
    def test_restart_vgpus_rhel_vm(self, gpu_vma):
        """
        Test VM with vGPU using GPUs spec, can be restarted successfully.
        """
        restart_and_check_gpu_exists(vm=gpu_vma)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::test_access_vgpus_rhel_vm"])
    @pytest.mark.polarion("CNV-8572")
    def test_access_vgpus_in_both_rhel_vm_using_same_gpu(self, gpu_vma, gpu_vmb):
        """
        Test vGPU is accessible in both the RHEL VMs, using same GPU, using GPUs spec.
        """
        vm_with_no_gpu = [
            vm.name
            for vm in [gpu_vma, gpu_vmb]
            if not get_num_gpu_devices_in_rhel_vm(vm=vm) == 1
        ]
        assert (
            not vm_with_no_gpu
        ), f"GPU does not exist in following vms: {vm_with_no_gpu}"


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_module, gpu_vma, node_mdevtype_gpu_vm",
    [
        pytest.param(
            {
                "dv_name": RHEL_LATEST_OS,
                "image": RHEL_LATEST["image_path"],
                "storage_class": py_config["default_storage_class"],
                "dv_size": RHEL_LATEST["dv_size"],
            },
            {
                "vm_name": "rhel-vgpu-gpus-spec-vm1",
                "template_labels": RHEL_LATEST_LABELS,
                "gpu_name": VGPU_DEVICE_NAME,
            },
            {
                "vm_name": "node-mdevtype-rhel-vgpu-gpus-spec-vm2",
                "template_labels": RHEL_LATEST_LABELS,
                "gpu_name": VGPU_GRID_T4_16Q_NAME,
            },
        ),
    ],
    indirect=True,
)
@pytest.mark.usefixtures(
    "skip_if_only_one_gpu_node",
    "hco_cr_with_node_specific_mdev_permitted_hostdevices",
)
class TestNodeMDEVTypeVGPURHELGPUSSpec:
    """
    Test vGPU with RHEL VM using GPUS Spec.
    """

    @pytest.mark.polarion("CNV-8744")
    def test_node_specific_permitted_hostdevices_vgpu_visible(
        self, gpu_vma, node_mdevtype_gpu_vm, gpu_nodes
    ):
        """
        Test Permitted HostDevice is visible and count updated under Capacity/Allocatable
        section for both nodes.

        Automatic Configuration of node specific mediated devices using nodeMediatedDeviceTypes
        Here we are using 'nodeMediatedDeviceTypes' in HCO CR, hence different nodes would
        have different mdevtype configured.
        Without the use of 'nodeMediatedDeviceTypes' in HCO CR, all the nodes, would have
        the same mdevtype configured for all the nodes.
        """
        verify_gpu_device_exists_on_node(
            gpu_nodes=[*gpu_nodes][:1], device_name=VGPU_DEVICE_NAME
        )
        verify_gpu_device_exists_on_node(
            gpu_nodes=[*gpu_nodes][1:2], device_name=VGPU_GRID_T4_16Q_NAME
        )
        verify_gpu_expected_count_updated_on_node(
            gpu_nodes=[*gpu_nodes][:1],
            device_name=VGPU_DEVICE_NAME,
            expected_count=MDEV_AVAILABLE_INSTANCES,
        )
        verify_gpu_expected_count_updated_on_node(
            gpu_nodes=[*gpu_nodes][1:2],
            device_name=VGPU_GRID_T4_16Q_NAME,
            expected_count=MDEV_GRID_T4_16Q_AVAILABLE_INSTANCES,
        )

    @pytest.mark.polarion("CNV-8745")
    def test_access_vgpus_using_node_mdevtype(
        self,
        gpu_vma,
        node_mdevtype_gpu_vm,
        vm_with_no_gpu,
    ):
        """
        Test vGPU is accessible in both the RHEL VMs, using GPUs spec.
        """
        assert (
            not vm_with_no_gpu
        ), f"GPU does not exist in following vms: {vm_with_no_gpu}"