"""
GPU PCI Passthrough VM
"""

import random

import pytest
from resources.resource import ResourceEditor

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
                ["bash", "-c", "/sbin/lspci -nnk | grep Tesla | cut -d ' ' -f 12"]
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
        yield pci_passthrough_vm


@pytest.fixture(scope="module")
def kubevirt_config_cm_with_gpu_hostdevices_feature_gate(kubevirt_config_cm):
    new_feature_gates = ["GPU", "HostDevices"]
    feature_gates = kubevirt_config_cm.instance["data"]["feature-gates"].split(",")

    if not all(
        new_feature_gate in feature_gates for new_feature_gate in new_feature_gates
    ):
        for new_feature_gate in new_feature_gates:
            if new_feature_gate not in feature_gates:
                feature_gates.append(new_feature_gate)
        config_map_dict = kubevirt_config_cm.instance.to_dict()
        config_map_dict["data"]["feature-gates"] = ",".join(feature_gates)
        with ResourceEditor(patches={kubevirt_config_cm: config_map_dict}):
            yield


@pytest.fixture(scope="class")
def kubevirt_config_cm_with_permitted_hostdevices(kubevirt_config_cm):
    config_map_dict = kubevirt_config_cm.instance.to_dict()
    config_map_dict["data"]["permittedHostDevices"] = (
        f"pciHostDevices:\n- pciVendorSelector: {GPU_DEVICE_ID.upper()}\n  "
        f"resourceName: {GPU_DEVICE_NAME}"
    )
    with ResourceEditor(patches={kubevirt_config_cm: config_map_dict}):
        yield
