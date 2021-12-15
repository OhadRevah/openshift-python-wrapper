from contextlib import contextmanager

from ocp_resources.datavolume import DataVolume
from ocp_resources.storage_class import StorageClass
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot

from utilities.constants import Images
from utilities.storage import get_images_server_url, write_file
from utilities.virt import VirtualMachineForTests


@contextmanager
def create_vm_for_snapshot_upgrade_tests(vm_name, namespace, client):
    dv = DataVolume(
        name=f"dv-{vm_name}",
        namespace=namespace,
        source="http",
        url=f"{get_images_server_url(schema='http')}{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
        storage_class=StorageClass.Types.CEPH_RBD,
        volume_mode=DataVolume.VolumeMode.BLOCK,
        access_modes=DataVolume.AccessMode.RWX,
        size=Images.Cirros.DEFAULT_DV_SIZE,
    ).to_dict()
    with VirtualMachineForTests(
        client=client,
        name=f"vm-{vm_name}",
        namespace=dv["metadata"]["namespace"],
        memory_requests=Images.Cirros.DEFAULT_MEMORY_SIZE,
        data_volume_template={"metadata": dv["metadata"], "spec": dv["spec"]},
    ) as vm:
        write_file(
            vm=vm,
            filename="first-file.txt",
            content="first-file",
        )
        yield vm


@contextmanager
def create_snapshot_for_upgrade(vm, client):
    """Creating a snapshot of vm and adding a text file to the vm"""
    with VirtualMachineSnapshot(
        name=f"snapshot-{vm.name}",
        namespace=vm.namespace,
        vm_name=vm.name,
        client=client,
    ) as vm_snapshot:
        vm_snapshot.wait_ready_to_use()
        write_file(
            vm=vm,
            filename="second-file.txt",
            content="second-file",
        )
        yield vm_snapshot
