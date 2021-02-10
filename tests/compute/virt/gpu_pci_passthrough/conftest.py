"""
GPU PCI Passthrough VM
"""

import random
import shlex

import pytest
from ocp_resources.resource import ResourceEditor

from tests.conftest import vm_instance_from_template
from utilities.constants import GPU_DEVICE_ID, GPU_DEVICE_NAME
from utilities.infra import run_ssh_commands


@pytest.fixture(scope="session")
def gpu_nodes(workers_ssh_executors, schedulable_nodes):
    """
    Find GPU Worker Node, where GPU device is allocated.
    """
    nodes = []
    for node in schedulable_nodes:
        out = run_ssh_commands(
            host=workers_ssh_executors[node.name],
            commands=[
                ["bash", "-c", "/sbin/lspci -nnk | grep Tesla | cut -d ' ' -f 10"]
            ],
        )
        if out[0].rstrip().strip("[]") == GPU_DEVICE_ID:
            nodes.append(node)
    return nodes


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
        node_selector=random.choice(gpu_nodes).name,
    ) as pci_passthrough_vm:
        if pci_passthrough_vm.os_flavor.startswith("win"):
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
                                "pciVendorSelector": GPU_DEVICE_ID.upper(),
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
