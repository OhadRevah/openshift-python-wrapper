# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV Storage snapshots tests
"""
import logging

import pytest
from ocp_resources.role_binding import RoleBinding
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot

from tests.storage.utils import set_permissions
from utilities.constants import UNPRIVILEGED_USER
from utilities.storage import write_file


LOGGER = logging.getLogger(__name__)


def check_snapshot_indication(snapshot, is_online):
    snapshot_indications = snapshot.instance.status.indications
    if is_online:
        assert "Online" in snapshot_indications
    else:
        assert not snapshot_indications


@pytest.fixture()
def snapshots_with_content(
    request,
    namespace,
    admin_client,
    cirros_vm,
):
    """
    Creates a requested number of snapshots with content
    The default behavior of the fixture is creating an offline
    snapshot unless {online_vm = True} declared in the test
    """
    vm_snapshots = []
    is_online_test = request.param.get("online_vm", False)
    for idx in range(request.param["number_of_snapshots"]):
        # write_file check if the vm is running and if not, start the vm
        # after the file have been written the function stops the vm
        write_file(
            vm=cirros_vm,
            filename=f"before-snap-{idx+1}.txt",
            content=f"before-snap-{idx+1}",
        )
        if is_online_test:
            cirros_vm.start(wait=True)
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
    check_snapshot_indication(snapshot=vm_snapshot, is_online=is_online_test)
    yield vm_snapshots

    for vm_snapshot in vm_snapshots:
        vm_snapshot.clean_up()


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
