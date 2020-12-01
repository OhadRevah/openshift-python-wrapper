# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV Storage snapshots tests
"""
import logging

import pytest
from resources.datavolume import DataVolume
from resources.role_binding import RoleBinding
from resources.storage_class import StorageClass
from resources.virtual_machine_snapshot import VirtualMachineSnapshot

from tests.conftest import UNPRIVILEGED_USER
from tests.storage.utils import set_permissions
from utilities import console
from utilities.infra import Images
from utilities.storage import get_images_external_http_server
from utilities.virt import VirtualMachineForTests


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def ocs_storage_class(admin_client):
    """
    Get the OCS storage class if configured
    """
    for sc in StorageClass.get(
        dyn_client=admin_client, name=StorageClass.Types.CEPH_RBD
    ):
        return sc


@pytest.fixture(scope="session")
def skip_test_if_no_ocs_sc(ocs_storage_class):
    """
    Skip test if no OCS storage class available
    """
    if not ocs_storage_class:
        pytest.skip("Skipping test, OCS storage class is not deployed")


@pytest.fixture()
def cirros_vm(
    request,
    admin_client,
    namespace,
):
    """
    Create a VM with a DV that resides on OCS
    """
    dv = DataVolume(
        name=f"dv-{request.param['vm_name']}",
        namespace=namespace.name,
        source="http",
        url=f"{get_images_external_http_server()}{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
        storage_class=StorageClass.Types.CEPH_RBD,
        volume_mode=DataVolume.VolumeMode.BLOCK,
        access_modes=DataVolume.AccessMode.RWX,
        size=Images.Cirros.DEFAULT_DV_SIZE,
    ).to_dict()
    dv_metadata = dv["metadata"]
    with VirtualMachineForTests(
        client=admin_client,
        name=request.param["vm_name"],
        namespace=dv_metadata["namespace"],
        memory_requests=Images.Cirros.DEFAULT_MEMORY_SIZE,
        data_volume_template={"metadata": dv_metadata, "spec": dv["spec"]},
    ) as vm:
        yield vm


@pytest.fixture()
def snapshots_with_content(
    request,
    namespace,
    admin_client,
    cirros_vm,
):
    """
    Creates a requested number of snapshots with content
    """
    vm_snapshots = []
    for idx in range(request.param["number_of_snapshots"]):
        write_file(
            vm=cirros_vm,
            filename=f"before-snap-{idx+1}.txt",
            content=f"before-snap-{idx+1}",
        )
        with VirtualMachineSnapshot(
            name=f"snapshot-{cirros_vm.name}-number-{idx+1}",
            namespace=cirros_vm.namespace,
            vm_name=cirros_vm.name,
            client=admin_client,
            teardown=False,
        ) as vm_snapshot:
            vm_snapshots.append(vm_snapshot)
            vm_snapshot.wait_ready_to_use()
            write_file(
                vm=cirros_vm,
                filename=f"after-snap-{idx+1}.txt",
                content=f"after-snap-{idx+1}",
            )
    yield vm_snapshots

    for vm_snapshot in vm_snapshots:
        vm_snapshot.clean_up()


def write_file(vm, filename, content):
    vm.start(wait=True)
    with console.Cirros(vm=vm) as vm_console:
        vm_console.sendline(f"echo '{content}' >> {filename}")
    vm.stop(wait=True)


@pytest.fixture()
def permissions_for_dv(namespace):
    """
    Sets DV permissions for an unprivileged client
    """
    with set_permissions(
        role_name="datavolume-cluster-role",
        verbs=["*"],
        permissions_to_resources=["datavolumes", "datavolumes/source"],
        binding_name="role-bind-data-volume",
        namespace=namespace.name,
        subjects_kind="User",
        subjects_name=UNPRIVILEGED_USER,
        subjects_api_group=RoleBinding.api_group,
    ):
        yield
