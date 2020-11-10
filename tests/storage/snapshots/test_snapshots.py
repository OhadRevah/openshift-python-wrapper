# -*- coding: utf-8 -*-

"""
Snapshots tests
"""

import logging

import pytest
from kubernetes.client.rest import ApiException
from resources.virtual_machine_restore import VirtualMachineRestore
from resources.virtual_machine_snapshot import VirtualMachineSnapshot
from utilities import console


LOGGER = logging.getLogger(__name__)


pytestmark = pytest.mark.usefixtures(
    "namespace",
    "skip_test_if_no_ocs_sc",
)

LS_COMMAND = "ls -1 | sort | tr '\n' ' '"
ERROR_MSG_VM_IS_RUNNING = (
    r".*virtualmachinerestore-validator.snapshot.kubevirt.io.*"
    r"denied the request: VirtualMachine.*is running.*"
)

VIRTUAL_MACHINES_SNAPSHOT_FORBIDDEN = (
    r".*virtualmachinesnapshots.snapshot.kubevirt.io is forbidden: User"
)
VIRTUAL_MACHINE_RESTORE_FORBIDDEN = (
    r".*virtualmachinerestores.snapshot.kubevirt.io is forbidden: User"
)
CANNOT_CREATE_RESOURCE = r"cannot create resource"
CANNOT_LIST_RESOURCE = r"cannot list resource"
VIRTUAL_MACHINES_SNAPSHOTS = r"virtualmachinesnapshots.*snapshot.kubevirt.io"
VIRTUAL_MACHINE_RESTORES = r"virtualmachinerestores.*snapshot.kubevirt.io"
IN_NAMESPACE = r"in the namespace"

ERROR_MSG_USER_CANNOT_CREATE_VM_RESTORE = (
    f"{VIRTUAL_MACHINE_RESTORE_FORBIDDEN}.*{CANNOT_CREATE_RESOURCE}.*"
    f"{VIRTUAL_MACHINE_RESTORES}.*{IN_NAMESPACE}.*"
)
ERROR_MSG_USER_CANNOT_CREATE_VM_SNAPSHOTS = (
    f"{VIRTUAL_MACHINES_SNAPSHOT_FORBIDDEN}.*{CANNOT_CREATE_RESOURCE}.*"
    f"{VIRTUAL_MACHINES_SNAPSHOTS}.*{IN_NAMESPACE}.*"
)
ERROR_MSG_USER_CANNOT_LIST_VM_SNAPSHOTS = (
    f"{VIRTUAL_MACHINES_SNAPSHOT_FORBIDDEN}.*{CANNOT_LIST_RESOURCE}.*"
    f"{VIRTUAL_MACHINES_SNAPSHOTS}.*{IN_NAMESPACE}.*"
)
ERROR_MSG_USER_CANNOT_LIST_VM_RESTORE = (
    f"{VIRTUAL_MACHINE_RESTORE_FORBIDDEN}.*{CANNOT_LIST_RESOURCE}.*"
    f"{VIRTUAL_MACHINE_RESTORES}.*{IN_NAMESPACE}.*"
)


def run_command_on_cirros_vm_and_check_output(vm, command, expected_result):
    with console.Cirros(vm=vm) as vm_console:
        vm_console.sendline(command)
        vm_console.expect(expected_result, timeout=20)


def expected_output_after_restore(snapshot_number):
    """
    Returns a string representing the list of files that should exist in the VM (sorted)
    after a restore snapshot was performed

    Args:
        snapshot_number (int): The snapshot number that was restored

    Returns:
        string: the list of files that should exist on the VM after restore operation was performed
    """
    files = []
    for idx in range(snapshot_number - 1):
        files.append(f"before-snap-{idx+1}.txt")
        files.append(f"after-snap-{idx+1}.txt")
    files.append(f"before-snap-{snapshot_number}.txt ")
    files.sort()
    return " ".join(files)


def fail_to_create_snapshot_no_permissions(snapshot_name, namespace, vm_name, client):
    with pytest.raises(
        ApiException,
        match=ERROR_MSG_USER_CANNOT_CREATE_VM_SNAPSHOTS,
    ):
        with VirtualMachineSnapshot(
            name=snapshot_name,
            namespace=namespace,
            vm_name=vm_name,
            client=client,
        ):
            return


class TestRestoreSnapshots:
    @pytest.mark.parametrize(
        "cirros_vm, snapshots_with_content, expected_results, snapshots_to_restore_idx",
        [
            pytest.param(
                {"vm_name": "vm-cnv-4789"},
                {"number_of_snapshots": 1},
                [expected_output_after_restore(1)],
                [0],
                marks=pytest.mark.polarion("CNV-4789"),
                id="test_restore_basic_snapshot",
            ),
            pytest.param(
                {"vm_name": "vm-cnv-4865"},
                {"number_of_snapshots": 3},
                [expected_output_after_restore(2)],
                [1],
                marks=pytest.mark.polarion("CNV-4865"),
                id="test_restore_middle_snapshot",
            ),
            pytest.param(
                {"vm_name": "vm-cnv-4843"},
                {"number_of_snapshots": 3},
                [
                    expected_output_after_restore(3),
                    expected_output_after_restore(2),
                    expected_output_after_restore(1),
                ],
                [2, 1, 0],
                marks=pytest.mark.polarion("CNV-4843"),
                id="test_restore_all_snapshots",
            ),
        ],
        indirect=["cirros_vm", "snapshots_with_content"],
    )
    def test_restore_snapshots(
        self,
        cirros_vm,
        snapshots_with_content,
        expected_results,
        snapshots_to_restore_idx,
    ):
        for idx in range(len(snapshots_to_restore_idx)):
            snap_idx = snapshots_to_restore_idx[idx]
            with VirtualMachineRestore(
                name=f"restore-snapshot-{snap_idx}",
                namespace=cirros_vm.namespace,
                vm_name=cirros_vm.name,
                snapshot_name=snapshots_with_content[snap_idx].name,
            ) as vm_restore:
                vm_restore.wait_complete()
                cirros_vm.start(wait=True)
                run_command_on_cirros_vm_and_check_output(
                    vm=cirros_vm,
                    command=LS_COMMAND,
                    expected_result=expected_results[idx],
                )
                cirros_vm.stop(wait=True)

    @pytest.mark.parametrize(
        "cirros_vm, snapshots_with_content",
        [
            pytest.param(
                {"vm_name": "vm-cnv-5048"},
                {"number_of_snapshots": 1},
                marks=pytest.mark.polarion("CNV-5048"),
            ),
        ],
        indirect=True,
    )
    def test_restore_snapshot_while_vm_is_running(
        self,
        cirros_vm,
        snapshots_with_content,
    ):
        cirros_vm.start(wait=True)
        with pytest.raises(
            ApiException,
            match=ERROR_MSG_VM_IS_RUNNING,
        ):
            with VirtualMachineRestore(
                name="restore-snapshot-cnv-5048",
                namespace=cirros_vm.namespace,
                vm_name=cirros_vm.name,
                snapshot_name=snapshots_with_content[0].name,
            ):
                return

    @pytest.mark.parametrize(
        "cirros_vm, snapshots_with_content, namespace",
        [
            pytest.param(
                {"vm_name": "vm-cnv-5049"},
                {"number_of_snapshots": 1},
                {"unprivileged_client": None},
                marks=pytest.mark.polarion("CNV-5049"),
            ),
        ],
        indirect=True,
    )
    def test_fail_restore_vm_with_unprivileged_client(
        self,
        cirros_vm,
        snapshots_with_content,
        unprivileged_client,
    ):
        with pytest.raises(
            ApiException,
            match=ERROR_MSG_USER_CANNOT_CREATE_VM_RESTORE,
        ):
            with VirtualMachineRestore(
                client=unprivileged_client,
                name="restore-snapshot-cnv-5049-unprivileged",
                namespace=cirros_vm.namespace,
                vm_name=cirros_vm.name,
                snapshot_name=snapshots_with_content[0].name,
            ):
                return

    @pytest.mark.parametrize(
        "cirros_vm, snapshots_with_content",
        [
            pytest.param(
                {"vm_name": "vm-cnv-5084"},
                {"number_of_snapshots": 1},
                marks=pytest.mark.polarion("CNV-5084"),
                id="test_that_restore_the_same_snapshot_twice ",
            ),
        ],
        indirect=True,
    )
    def test_restore_same_snapshot_twice(
        self,
        cirros_vm,
        snapshots_with_content,
    ):
        with VirtualMachineRestore(
            name="restore-snapshot-cnv-5084-first",
            namespace=cirros_vm.namespace,
            vm_name=cirros_vm.name,
            snapshot_name=snapshots_with_content[0].name,
        ) as first_restore:
            first_restore.wait_complete()
            with VirtualMachineRestore(
                name="restore-snapshot-cnv-5084-second",
                namespace=cirros_vm.namespace,
                vm_name=cirros_vm.name,
                snapshot_name=snapshots_with_content[0].name,
            ) as second_restore:
                second_restore.wait_complete()
                cirros_vm.start(wait=True)
                run_command_on_cirros_vm_and_check_output(
                    vm=cirros_vm,
                    command=LS_COMMAND,
                    expected_result=expected_output_after_restore(1),
                )


@pytest.mark.parametrize(
    "cirros_vm, snapshots_with_content",
    [
        pytest.param(
            {"vm_name": "vm-cnv-4866"},
            {"number_of_snapshots": 2},
            marks=pytest.mark.polarion("CNV-4866"),
        ),
    ],
    indirect=True,
)
def test_remove_vm_with_snapshots(
    cirros_vm,
    snapshots_with_content,
):
    cirros_vm.delete(wait=True)
    for snapshot in snapshots_with_content:
        assert snapshot.instance.status.readyToUse


@pytest.mark.parametrize(
    "cirros_vm, snapshots_with_content, expected_result",
    [
        pytest.param(
            {"vm_name": "vm-cnv-4870"},
            {"number_of_snapshots": 2},
            "after-snap-1.txt after-snap-2.txt before-snap-1.txt before-snap-2.txt",
            marks=pytest.mark.polarion("CNV-4870"),
        ),
    ],
    indirect=["cirros_vm", "snapshots_with_content"],
)
def test_remove_snapshots_while_vm_is_running(
    cirros_vm,
    snapshots_with_content,
    expected_result,
):
    cirros_vm.start(wait=True)
    for idx in range(len(snapshots_with_content)):
        snapshots_with_content[idx].delete(wait=True)
        run_command_on_cirros_vm_and_check_output(
            vm=cirros_vm, command=LS_COMMAND, expected_result=expected_result
        )
        cirros_vm.restart(wait=True)
        run_command_on_cirros_vm_and_check_output(
            vm=cirros_vm, command=LS_COMMAND, expected_result=expected_result
        )


@pytest.mark.parametrize(
    "namespace, resource, error_msg",
    [
        pytest.param(
            {"unprivileged_client": None},
            VirtualMachineSnapshot,
            ERROR_MSG_USER_CANNOT_LIST_VM_SNAPSHOTS,
            marks=pytest.mark.polarion("CNV-5050"),
        ),
        pytest.param(
            {"unprivileged_client": None},
            VirtualMachineRestore,
            ERROR_MSG_USER_CANNOT_LIST_VM_RESTORE,
            marks=pytest.mark.polarion("CNV-5331"),
        ),
    ],
    indirect=["namespace"],
)
def test_unprivileged_client_fails_to_list_resources(
    namespace, unprivileged_client, resource, error_msg
):
    with pytest.raises(
        ApiException,
        match=error_msg,
    ):
        list(resource.get(dyn_client=unprivileged_client, namespace=namespace.name))
        return


@pytest.mark.parametrize(
    "cirros_vm, namespace",
    [
        pytest.param(
            {"vm_name": "vm-cnv-4867"},
            {"unprivileged_client": None},
            marks=pytest.mark.polarion("CNV-4867"),
        ),
    ],
    indirect=True,
)
def test_fail_to_snapshot_with_unprivileged_client_no_permissions(
    cirros_vm,
    unprivileged_client,
):
    fail_to_create_snapshot_no_permissions(
        snapshot_name="snapshot-cnv-4867-unprivileged",
        namespace=cirros_vm.namespace,
        vm_name=cirros_vm.name,
        client=unprivileged_client,
    )


@pytest.mark.parametrize(
    "cirros_vm, namespace",
    [
        pytest.param(
            {"vm_name": "vm-cnv-4868"},
            {"unprivileged_client": None},
            marks=pytest.mark.polarion("CNV-4868"),
        ),
    ],
    indirect=True,
)
def test_fail_to_snapshot_with_unprivileged_client_dv_permissions(
    cirros_vm,
    permissions_for_dv,
    unprivileged_client,
):
    fail_to_create_snapshot_no_permissions(
        snapshot_name="snapshot-cnv-4868-unprivileged",
        namespace=cirros_vm.namespace,
        vm_name=cirros_vm.name,
        client=unprivileged_client,
    )
