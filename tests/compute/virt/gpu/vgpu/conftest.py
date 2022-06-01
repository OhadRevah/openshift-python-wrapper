"""
vGPU VM
"""
import pytest

from utilities.constants import (
    MDEV_GRID_T4_16Q_NAME,
    MDEV_GRID_T4_16Q_TYPE,
    MDEV_NAME,
    MDEV_TYPE,
    VGPU_DEVICE_NAME,
    VGPU_GRID_T4_16Q_NAME,
)
from utilities.hco import ResourceEditorValidateHCOReconcile, wait_for_hco_conditions
from utilities.infra import ExecCommandOnPod


@pytest.fixture(scope="session")
def non_existent_mdev_bus_nodes(utility_pods, gpu_nodes):
    """
    Check if the mdev_bus needed for vGPU is availble.

    On the Worker Node on which GPU Device exists, Check if the
    mdev_bus needed for vGPU is availble.
    If it's not available, this means the simple-kmod-driver-container
    Pod might not be in running state in nvidia-driver namespace.
    """
    desired_bus = "mdev_bus"
    non_existent_mdev_bus_nodes = []
    for node in gpu_nodes.keys():
        pod_exec = ExecCommandOnPod(utility_pods=utility_pods, node=node)
        if desired_bus not in pod_exec.exec(
            command=f"ls /sys/class | grep {desired_bus} || true"
        ):
            non_existent_mdev_bus_nodes.append(node.name)
    if non_existent_mdev_bus_nodes:
        pytest.fail(
            msg=(
                f"On these nodes: {non_existent_mdev_bus_nodes} {desired_bus} is not available."
                "Ensure that in 'nvidia-driver' namespace simple-kmod-driver-container Pod is Running."
            )
        )


@pytest.fixture(scope="class")
def hco_cr_with_mdev_permitted_hostdevices(
    admin_client, hco_namespace, hyperconverged_resource_scope_class
):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_class: {
                "spec": {
                    "mediatedDevicesConfiguration": {
                        "mediatedDevicesTypes": [MDEV_TYPE]
                    },
                    "permittedHostDevices": {
                        "mediatedDevices": [
                            {
                                "mdevNameSelector": MDEV_NAME,
                                "resourceName": VGPU_DEVICE_NAME,
                            }
                        ]
                    },
                }
            }
        },
    ):
        wait_for_hco_conditions(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )
        yield


@pytest.fixture(scope="class")
def hco_cr_with_node_specific_mdev_permitted_hostdevices(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_class,
    gpu_nodes,
):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_class: {
                "spec": {
                    "mediatedDevicesConfiguration": {
                        "mediatedDevicesTypes": [MDEV_TYPE],
                        "nodeMediatedDeviceTypes": [
                            {
                                "mediatedDevicesTypes": [MDEV_GRID_T4_16Q_TYPE],
                                "nodeSelector": {
                                    "kubernetes.io/hostname": [*gpu_nodes][1].name
                                },
                            }
                        ],
                    },
                    "permittedHostDevices": {
                        "mediatedDevices": [
                            {
                                "mdevNameSelector": MDEV_NAME,
                                "resourceName": VGPU_DEVICE_NAME,
                            },
                            {
                                "mdevNameSelector": MDEV_GRID_T4_16Q_NAME,
                                "resourceName": VGPU_GRID_T4_16Q_NAME,
                            },
                        ]
                    },
                }
            }
        },
    ):
        wait_for_hco_conditions(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )
        yield
