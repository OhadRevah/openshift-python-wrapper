import pytest
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot

from tests.chaos.constants import VM_LABEL
from utilities.constants import OS_FLAVOR_CIRROS, Images
from utilities.storage import create_cirros_ceph_dv
from utilities.virt import VirtualMachineForTests, running_vm


@pytest.fixture()
def chaos_snapshot_dv(chaos_namespace):
    """
    Define a DV that resides on OCS for use by a VM
    """
    yield create_cirros_ceph_dv(name="chaos", namespace=chaos_namespace.name)


@pytest.fixture()
def chaos_snapshot_vm(admin_client, chaos_namespace, chaos_snapshot_dv):
    dv_dict = chaos_snapshot_dv.to_dict()
    with VirtualMachineForTests(
        client=admin_client,
        name="vm-chaos-snapshot",
        namespace=chaos_namespace.name,
        os_flavor=OS_FLAVOR_CIRROS,
        memory_requests=Images.Cirros.DEFAULT_MEMORY_SIZE,
        data_volume_template={"metadata": dv_dict["metadata"], "spec": dv_dict["spec"]},
        additional_labels=VM_LABEL,
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)
        yield vm


@pytest.fixture()
def chaos_online_snapshots(
    request,
    admin_client,
    chaos_snapshot_vm,
):
    vm_snapshots = []
    for idx in range(request.param["number_of_snapshots"]):
        with VirtualMachineSnapshot(
            name=f"snapshot-{chaos_snapshot_vm.name}-{idx}",
            namespace=chaos_snapshot_vm.namespace,
            vm_name=chaos_snapshot_vm.name,
            client=admin_client,
            teardown=False,
        ) as vm_snapshot:
            vm_snapshots.append(vm_snapshot)
            vm_snapshot.wait_ready_to_use()
    yield vm_snapshots
