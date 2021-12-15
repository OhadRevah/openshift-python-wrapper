import logging
from concurrent.futures import ThreadPoolExecutor

import pytest
from ocp_resources.node_network_configuration_enactment import (  # noqa: N813
    NodeNetworkConfigurationEnactment as nnce,
)

from utilities.infra import BUG_STATUS_CLOSED
from utilities.network import LinuxBridgeNodeNetworkConfigurationPolicy


LOGGER = logging.getLogger(__name__)

PROGRESSING = nnce.Conditions.Type.PROGRESSING
PENDING = nnce.Conditions.Type.PENDING
NUM_OF_DESIRED_WORKERS = 3


@pytest.fixture()
def skip_if_not_three_nodes(schedulable_nodes):
    if len(schedulable_nodes) != NUM_OF_DESIRED_WORKERS:
        pytest.skip(f"Only run on {NUM_OF_DESIRED_WORKERS} worker nodes")


def nnce_status_for_worker(nncp_policy, worker):
    nncp_policy.wait_for_conditions()
    nnce_worker_resources = nncp_policy.node_nnce(node_name=worker.name)
    LOGGER.info(
        f"Complete condition of {nnce_worker_resources.name} NNCE : {nnce_worker_resources.instance.status.conditions}"
    )
    for nnce_state in nnce_worker_resources.instance.status.conditions:
        if nnce_state["status"] == nncp_policy.Condition.Status.TRUE:
            worker_state = nnce_state["type"]
            LOGGER.info(
                f"Initial status of {nnce_worker_resources.name} when policy is applied : {worker_state}"
            )
            return worker_state


@pytest.fixture()
def maxunavailable_input_for_bridge_creation(
    request, hosts_common_available_ports, unprivileged_client, utility_pods
):
    nncp_policy = LinuxBridgeNodeNetworkConfigurationPolicy(
        name="maxunavailable-policy",
        bridge_name="brmaxunavail",
        ports=[hosts_common_available_ports[0]],
        worker_pods=utility_pods,
        max_unavailable=request.param,
    )
    yield nncp_policy
    # we need to wait for final status because policy can't be deleted until it reaches a final state.
    # Webhook returns 403 forbidden if abort/delete operation is performed.
    nncp_policy.wait_for_status_success()
    nncp_policy.clean_up()


def enable_threading_get_intermediate_nnce_nodes(policy, workers):
    actual_state = []
    with ThreadPoolExecutor(max_workers=NUM_OF_DESIRED_WORKERS) as executor:
        for worker in workers:
            nnce_state = executor.submit(nnce_status_for_worker, policy, worker)
            actual_state += [nnce_state.result()]
        LOGGER.info(f"Combined Status of threads: {actual_state}")
        return actual_state


@pytest.mark.parametrize(
    "maxunavailable_input_for_bridge_creation, expected_state",
    [
        pytest.param(
            "10%",
            [PENDING, PENDING, PROGRESSING],
            id="maxunavailable_input_for_bridge_creation_10%",
            marks=pytest.mark.polarion("CNV-7539"),
        ),
        pytest.param(
            "100%",
            [PROGRESSING, PROGRESSING, PROGRESSING],
            id="maxunavailable_input_for_bridge_creation_100%",
            marks=(
                pytest.mark.polarion("CNV-7541"),
                pytest.mark.bugzilla(
                    2029767, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
            ),
        ),
        pytest.param(
            "ab%vn",
            [PROGRESSING, PROGRESSING, PROGRESSING],
            id="maxunavailable_input_for_bridge_creation_randomdata",
            marks=(
                pytest.mark.polarion("CNV-7546"),
                pytest.mark.bugzilla(
                    2024526, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
            ),
        ),
    ],
    indirect=["maxunavailable_input_for_bridge_creation"],
)
def test_create_policy_get_status(
    skip_if_not_three_nodes,
    schedulable_nodes,
    maxunavailable_input_for_bridge_creation,
    expected_state,
):
    maxunavailable_input_for_bridge_creation.create()
    actual_state = enable_threading_get_intermediate_nnce_nodes(
        policy=maxunavailable_input_for_bridge_creation,
        workers=schedulable_nodes,
    )
    LOGGER.info(
        f"Comparing actutal_state : {actual_state} & expected_state : {expected_state}"
    )
    assert sorted(actual_state) == sorted(expected_state)
