"""
Create non-evictable VM with RWO Storage and evictionStrategy=True that should fire the VMCannotBeEvicted alert
"""

import pytest
from ocp_resources.storage_class import StorageClass

from tests.os_params import FEDORA_LATEST
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


@pytest.fixture()
def non_evictable_vm(namespace, unprivileged_client, data_volume_scope_function):
    name = "non-evictable-vm"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        eviction=True,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        data_volume=data_volume_scope_function,
    ) as vm:
        running_vm(vm=vm, check_ssh_connectivity=False)
        yield vm


@pytest.mark.parametrize(
    "data_volume_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-non-evictable-vm",
                "image": FEDORA_LATEST["image_path"],
                "storage_class": StorageClass.Types.HOSTPATH,
                "dv_size": FEDORA_LATEST["dv_size"],
            },
            marks=pytest.mark.polarion("CNV-7484"),
        ),
    ],
    indirect=True,
)
def test_non_evictable_vm_fired_alert(
    prometheus,
    non_evictable_vm,
):
    prometheus.alert_sampler(alert="VMCannotBeEvicted")
