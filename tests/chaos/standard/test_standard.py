import pytest

from tests.chaos.constants import CHAOS_ENGINE_NAME, LITMUS_NAMESPACE, ExperimentNames
from utilities.constants import TIMEOUT_30SEC
from utilities.virt import running_vm


@pytest.mark.parametrize(
    "chaos_engine_from_yaml",
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
                    {"name": "TOTAL_CHAOS_DURATION", "value": str(TIMEOUT_30SEC)},
                    {"name": "CHAOS_NAMESPACE", "value": LITMUS_NAMESPACE},
                    {"name": "CHAOSENGINE", "value": CHAOS_ENGINE_NAME},
                ],
            },
        )
    ],
    indirect=True,
)
@pytest.mark.chaos
@pytest.mark.polarion("CNV-5428")
def test_pod_delete_openshift_apiserver(
    admin_client,
    litmus_service_account,
    cluster_role_pod_delete,
    litmus_cluster_role_binding,
    vm_cirros_chaos,
    kraken_container,
    running_chaos_engine,
):
    """
    This experiment tests the robustness of the cluster
    by killing a random apiserver pod in the `openshift-apiserver` namespace
    and asserting that a given running VMI instance is still running before and after the test completes
    """
    assert kraken_container.wait()
    running_vm(
        vm=vm_cirros_chaos, wait_for_interfaces=False, check_ssh_connectivity=False
    )