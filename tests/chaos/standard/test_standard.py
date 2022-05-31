import pytest

from tests.chaos.constants import (
    CHAOS_NAMESPACE,
    LITMUS_NAMESPACE,
    VM_LABEL_KEY,
    VM_LABEL_VALUE,
    ExperimentNames,
)
from tests.chaos.utils.chaos_engine import Probe


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
                "k8s_probes": [
                    {
                        "name": "Check VM running before and after chaos injection",
                        "type": Probe.ProbeTypes.K8S,
                        "mode": Probe.ProbeModes.EDGE,
                        "group": "kubevirt.io",
                        "version": "v1alpha3",
                        "resource": "virtualmachineinstances",
                        "namespace": CHAOS_NAMESPACE,
                        "label_selector": f"{VM_LABEL_KEY}={VM_LABEL_VALUE}",
                        "operation": Probe.ProbeOperations.PRESENT,
                        "probe_timeout": 5,
                        "interval": 1,
                        "retries": 1,
                    }
                ],
                "components": [
                    {"name": "FORCE", "value": "true"},
                    {"name": "TOTAL_CHAOS_DURATION", "value": "30"},
                    {"name": "CHAOS_NAMESPACE", "value": LITMUS_NAMESPACE},
                    {"name": "CHAOSENGINE", "value": "chaos-engine"},
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
    chaos_engine_from_yaml,
    kraken_container,
):
    """
    This experiment tests the robustness of the cluster
    by killing a random apiserver pod in the `openshift-apiserver` namespace
    and asserting that a given running VMI instance is still running before and after the test completes
    """
    assert kraken_container.wait()
    chaos_engine_from_yaml.assert_experiment_probes()
