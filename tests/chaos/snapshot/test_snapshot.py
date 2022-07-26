import pytest
from ocp_resources.virtual_machine_restore import VirtualMachineRestore

from tests.chaos.constants import CHAOS_ENGINE_NAME, LITMUS_NAMESPACE, ExperimentNames
from utilities.constants import TIMEOUT_3MIN


@pytest.mark.parametrize(
    "chaos_engine_from_yaml, chaos_online_snapshots",
    [
        pytest.param(
            {
                "experiment_name": ExperimentNames.POD_DELETE,
                "app_info": {
                    "namespace": "openshift-apiserver",
                    "label": "apiserver=true",
                    "kind": "deployment",
                },
                "components": [
                    {"name": "FORCE", "value": "true"},
                    {"name": "TOTAL_CHAOS_DURATION", "value": str(TIMEOUT_3MIN)},
                    {"name": "CHAOS_NAMESPACE", "value": LITMUS_NAMESPACE},
                    {"name": "CHAOSENGINE", "value": CHAOS_ENGINE_NAME},
                    {"name": "CHAOS_INTERVAL", "value": "1"},
                    {"name": "PODS_AFFECTED_PERC", "value": "67"},
                ],
            },
            {"number_of_snapshots": 3},
        )
    ],
    indirect=True,
)
@pytest.mark.chaos
@pytest.mark.polarion("CNV-8260")
def test_pod_delete_openshift_apiserver_snapshot(
    admin_client,
    litmus_service_account,
    cluster_role_pod_delete,
    litmus_cluster_role_binding,
    chaos_snapshot_vm,
    running_chaos_engine,
    krkn_process,
    chaos_online_snapshots,
):
    """
    This experiment tests the robustness of the VM snapshot feature
    by killing random apiserver pods in the `openshift-apiserver` namespace
    and asserting that VM snapshots can be taken, restored and deleted during the process.
    """
    chaos_snapshot_vm.stop(wait=True)
    for idx, snapshot in enumerate(chaos_online_snapshots):
        with VirtualMachineRestore(
            name=f"restore-snapshot-{idx}",
            namespace=chaos_snapshot_vm.namespace,
            vm_name=chaos_snapshot_vm.name,
            snapshot_name=snapshot.name,
        ) as vm_restore:
            vm_restore.wait_complete()
        snapshot.clean_up()
    assert krkn_process.wait(), "Krkn process finished with errors."
