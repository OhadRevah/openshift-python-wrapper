"""
GPU PCI Passthrough VM
"""


import pytest
from ocp_resources.resource import ResourceEditor

from utilities.constants import GPU_DEVICE_ID, GPU_DEVICE_NAME, KERNEL_DRIVER
from utilities.infra import ResourceEditorValidateHCOReconcile


@pytest.fixture(scope="session")
def fail_if_device_unbound_to_vfiopci_driver(gpu_nodes):
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
                f"Ensure IOMMU and  {KERNEL_DRIVER} Machine Config is applied."
            )
        )


@pytest.fixture(scope="class")
def hco_cr_with_permitted_hostdevices(hyperconverged_resource_scope_class):
    with ResourceEditorValidateHCOReconcile(
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
        },
    ):
        yield


@pytest.fixture()
def updated_vm_gpus_spec(gpu_vm):
    vm_dict = gpu_vm.instance.to_dict()
    vm_spec_dict = vm_dict["spec"]["template"]["spec"]
    vm_spec_dict["domain"]["devices"].pop("hostDevices", "No key Found")
    ResourceEditor(patches={gpu_vm: vm_dict}, action="replace").update()
    ResourceEditor(
        patches={
            gpu_vm: {
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
