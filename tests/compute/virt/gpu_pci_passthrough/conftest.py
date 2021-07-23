"""
GPU PCI Passthrough VM
"""

import random
import shlex

import pytest
from ocp_resources.resource import ResourceEditor

from utilities.constants import GPU_DEVICE_ID, GPU_DEVICE_NAME, OS_FLAVOR_WINDOWS
from utilities.infra import run_ssh_commands
from utilities.virt import vm_instance_from_template


KERNEL_DRIVER = "vfio-pci"


@pytest.fixture(scope="session")
def gpu_nodes(workers_ssh_executors, schedulable_nodes):
    """
    Find GPU Worker Node, where GPU device is allocated.
    """
    nodes = {}
    for node in schedulable_nodes:
        out = run_ssh_commands(
            host=workers_ssh_executors[node.name],
            commands=[
                shlex.split("sudo /sbin/lspci -nnk | grep -A 3 '3D controller' || true")
            ],
        )[0]
        if GPU_DEVICE_ID in out:
            nodes.update({node: out})
    return nodes


@pytest.fixture(scope="session")
def fail_if_device_unbound_to_vfiopci_driver(workers_ssh_executors, gpu_nodes):
    """
    Fail if the Kernel Driver vfio-pci is not in use by the NVIDIA GPU Device.
    """
    device_unbound_nodes = []
    for node, output in gpu_nodes.items():
        if KERNEL_DRIVER not in output:
            device_unbound_nodes.append(node.name)
    if device_unbound_nodes:
        pytest.fail(
            msg=(
                f"On these nodes: {device_unbound_nodes} GPU Devices are not bound to the {KERNEL_DRIVER} Driver."
                f"Ensure IOMMU and VFIO-PCI Machine Config is applied."
            )
        )


@pytest.fixture(scope="session")
def skip_if_no_gpu_node(gpu_nodes):
    if not gpu_nodes:
        pytest.skip(msg="Only run on a Cluster with at-least one GPU Worker node")


@pytest.fixture(scope="class")
def pci_passthrough_vm(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_volume_scope_class,
    gpu_nodes,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume=golden_image_data_volume_scope_class,
        node_selector=random.choice([*gpu_nodes]).name,
    ) as pci_passthrough_vm:
        if pci_passthrough_vm.os_flavor.startswith(OS_FLAVOR_WINDOWS):
            # Install NVIDIA Drivers placed on the Windows-10 or win2k19 Images.
            run_ssh_commands(
                host=pci_passthrough_vm.ssh_exec,
                commands=[shlex.split("C:\\\\NVIDIA\\\\International\\\\setup.exe -s")],
            )
        yield pci_passthrough_vm


@pytest.fixture(scope="class")
def hco_cr_with_permitted_hostdevices(hyperconverged_resource_scope_class):
    with ResourceEditor(
        patches={
            hyperconverged_resource_scope_class: {
                "spec": {
                    "permittedHostDevices": {
                        "pciHostDevices": [
                            {
                                "pciDeviceSelector": GPU_DEVICE_ID,
                                "resourceName": GPU_DEVICE_NAME,
                            }
                        ]
                    }
                }
            }
        }
    ):
        yield


@pytest.fixture()
def updated_vm_gpus_spec(pci_passthrough_vm):
    vm_dict = pci_passthrough_vm.instance.to_dict()
    vm_spec_dict = vm_dict["spec"]["template"]["spec"]
    vm_spec_dict["domain"]["devices"].pop("hostDevices", "No key Found")
    ResourceEditor(patches={pci_passthrough_vm: vm_dict}, action="replace").update()
    ResourceEditor(
        patches={
            pci_passthrough_vm: {
                "spec": {
                    "template": {
                        "spec": {
                            "domain": {
                                "devices": {
                                    "gpus": [
                                        {
                                            "deviceName": GPU_DEVICE_NAME,
                                            "name": "gpus",
                                        }
                                    ]
                                }
                            }
                        }
                    }
                }
            }
        }
    ).update()
