"""
GPU PCI Passthrough VM
"""

import random
import shlex

import pytest

from utilities.constants import GPU_DEVICE_ID, OS_FLAVOR_WINDOWS
from utilities.infra import ExecCommandOnPod, run_ssh_commands
from utilities.virt import vm_instance_from_template


@pytest.fixture(scope="session")
def gpu_nodes(utility_pods, schedulable_nodes):
    """
    Find GPU Worker Node, where GPU device is allocated.
    """
    nodes = {}
    for node in schedulable_nodes:
        pod_exec = ExecCommandOnPod(utility_pods=utility_pods, node=node)
        out = pod_exec.exec(
            command="sudo /sbin/lspci -nnk | grep -A 3 '3D controller' || true"
        )
        if GPU_DEVICE_ID in out:
            nodes.update({node: out})
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
    golden_image_dv_scope_module_data_source_scope_class,
    gpu_nodes,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source=golden_image_dv_scope_module_data_source_scope_class,
        node_selector=random.choice([*gpu_nodes]).name,
    ) as pci_passthrough_vm:
        if pci_passthrough_vm.os_flavor.startswith(OS_FLAVOR_WINDOWS):
            # Install NVIDIA Drivers placed on the Windows-10 or win2k19 Images.
            run_ssh_commands(
                host=pci_passthrough_vm.ssh_exec,
                commands=[
                    shlex.split("C:\\\\NVIDIA\\\\gpu\\\\International\\\\setup.exe -s")
                ],
            )
        yield pci_passthrough_vm
