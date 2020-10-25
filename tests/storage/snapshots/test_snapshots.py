# -*- coding: utf-8 -*-

"""
Snapshots tests
"""

import logging

import pytest
from kubernetes.client.rest import ApiException
from resources.virtual_machine_restore import VirtualMachineRestore
from utilities import console


LOGGER = logging.getLogger(__name__)


pytestmark = pytest.mark.usefixtures(
    "namespace",
    "skip_test_if_no_ocs_sc",
)

LS_COMMAND = "ls -1 | sort | tr '\n' ' '"
ERROR_MSG_VM_IS_RUNNING = (
    r".*virtualmachinerestore-validator.snapshot.kubevirt.io.*|"
    r".*denied the request: VirtualMachine.*|.*is running.*"
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
                id="test restore basic snapshot",
            ),
            pytest.param(
                {"vm_name": "vm-cnv-4865"},
                {"number_of_snapshots": 3},
                [expected_output_after_restore(2)],
                [1],
                marks=pytest.mark.polarion("CNV-4865"),
                id="test restore middle snapshot",
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
                id="test restore all snapshots",
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
        # TODO: use cirros_vm.restart(wait=True) - when function is fixed
        cirros_vm.stop(wait=True)
        cirros_vm.start(wait=True)
        run_command_on_cirros_vm_and_check_output(
            vm=cirros_vm, command=LS_COMMAND, expected_result=expected_result
        )
