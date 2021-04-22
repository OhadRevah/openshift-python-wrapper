import logging

from ocp_resources.daemonset import DaemonSet
from ocp_resources.deployment import Deployment
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.resource import Resource, ResourceEditor
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from openshift.dynamic.exceptions import NotFoundError
from pytest_testconfig import config as py_config

from utilities.constants import TIMEOUT_4MIN, TIMEOUT_10MIN


DEFAULT_HCO_CONDITIONS = {
    Resource.Condition.AVAILABLE: Resource.Condition.Status.TRUE,
    Resource.Condition.PROGRESSING: Resource.Condition.Status.FALSE,
    Resource.Condition.RECONCILE_COMPLETE: Resource.Condition.Status.TRUE,
    Resource.Condition.DEGRADED: Resource.Condition.Status.FALSE,
    Resource.Condition.UPGRADEABLE: Resource.Condition.Status.TRUE,
}
DEFAULT_HCO_PROGRESSING_CONDITIONS = {
    Resource.Condition.PROGRESSING: Resource.Condition.Status.TRUE,
}
LOGGER = logging.getLogger(__name__)


def wait_for_hco_conditions(
    admin_client,
    conditions=DEFAULT_HCO_CONDITIONS,
    sleep=5,
    # number_of_consecutive_checks is the number of time to repeat the status check to make sure the
    # transition is done. In some case we can get into situation when a ready status is because the
    # process was not start yet, or part of the component are ready but others didn't start the process
    # yet. In these case we'll use a higher value in number_of_consecutive_checks to make sure the ready
    # status is consistence.
    number_of_consecutive_checks=1,
):
    """
    Checking HCO conditions.
    If conditions are not met in the given time Raise TimeoutExpiredError.
    """
    expected_hco_conditions = conditions

    actual_hco_conditions = {}
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=sleep,
        func=lambda: list(
            HyperConverged.get(
                dyn_client=admin_client, namespace=py_config["hco_namespace"]
            )
        ),
        exceptions=NotFoundError,
    )
    current_check = 0
    try:
        for sample in samples:
            if sample[0].instance.get("status", {}).get("conditions"):
                resource_conditions = sample[0].instance.status.conditions
                actual_hco_conditions = {
                    condition.type: condition.status
                    for condition in resource_conditions
                    if condition.type in expected_hco_conditions.keys()
                }

                if actual_hco_conditions == expected_hco_conditions:
                    current_check = current_check + 1
                    if current_check >= number_of_consecutive_checks:
                        return
                else:
                    current_check = 0

    except TimeoutExpiredError:
        LOGGER.error(
            f"Expected conditions: {expected_hco_conditions}. Actual "
            f"conditions: {actual_hco_conditions}"
        )
        raise


def wait_for_ds(ds):
    LOGGER.info(f"Waiting for daemonset {ds.name} to be up to date.")
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_4MIN,
        sleep=5,
        func=lambda: ds.instance.to_dict(),
    )
    try:
        for sample in samples:
            status = sample.get("status")
            metadata = sample.get("metadata")
            if metadata.get("generation") == status.get("observedGeneration") and (
                status.get("desiredNumberScheduled")
                == status.get("currentNumberScheduled")
                == status.get("updatedNumberScheduled")
            ):
                break
    except TimeoutExpiredError:
        LOGGER.error(f"Timeout waiting for daemonset {ds.name} to be up to date.")
        raise


def wait_for_dp(dp):
    LOGGER.info(f"Waiting for deployment {dp.name} to be up to date.")
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_4MIN,
        sleep=5,
        func=lambda: dp.instance.to_dict(),
    )
    try:
        for sample in samples:
            status = sample.get("status")
            metadata = sample.get("metadata")
            if metadata.get("generation") == status.get(
                "observedGeneration"
            ) and status.get("replicas") == status.get("updatedReplicas"):
                break
    except TimeoutExpiredError:
        LOGGER.error(f"Timeout waiting for deployment {dp.name} to be up to date.")
        raise


def apply_np_changes(
    admin_client, hco, hco_namespace, infra_placement=None, workloads_placement=None
):
    current_infra = hco.instance.to_dict()["spec"].get("infra")
    current_workloads = hco.instance.to_dict()["spec"].get("workloads")
    target_infra = infra_placement if infra_placement is not None else current_infra
    target_workloads = (
        workloads_placement if workloads_placement is not None else current_workloads
    )
    if target_workloads != current_workloads or target_infra != current_infra:
        reseditor = ResourceEditor(
            patches={
                hco: {
                    "spec": {
                        "infra": target_infra or None,
                        "workloads": target_workloads or None,
                    }
                }
            }
        )
        LOGGER.info("Updating HCO with node placement.")
        reseditor.update()
        LOGGER.info("Waiting for HCO to report progressing condition.")
        wait_for_hco_conditions(
            admin_client=admin_client,
            conditions=DEFAULT_HCO_PROGRESSING_CONDITIONS,
            sleep=5,
        )
        LOGGER.info(
            "Waiting for all HCO conditions to detect that it's back to a stable configuration."
        )
        wait_for_hco_conditions(
            admin_client=admin_client,
            conditions=DEFAULT_HCO_CONDITIONS,
            sleep=5,
            number_of_consecutive_checks=6,
        )
        # unfortunately at this time we are not really done:
        # HCO propagated the change to components operators that propagated it
        # to their operands (deployments and daemonsets)
        # so all the CNV operators reports progressing=False and even HCO reports progressing=False
        # but deployment and daemonsets controllers has still to kill and restart pods.
        # with the following lines we can wait for all the deployment and daemonsets in
        # openshift-cnv namespace to be back to uptodate status.
        # The remain issue is that if we check it too fast, we can even check before
        # deployment and daemonsets controller report uptodate=false.
        # We have also to compare the observedGeneration with the generation number
        # to be sure that the relevant controller already updated the status
        for ds in DaemonSet.get(
            dyn_client=admin_client,
            namespace=hco_namespace.name,
        ):
            wait_for_ds(ds=ds)
        for dp in Deployment.get(
            dyn_client=admin_client,
            namespace=hco_namespace.name,
        ):
            wait_for_dp(dp=dp)
    else:
        LOGGER.info("No actual changes to node placement configuration, skipping")


def add_labels_to_nodes(nodes, node_labels):
    """
    This function is going to add label to each node.
    Returns a node_resources and dictionary of lableled nodes.
    """
    node_resources = []
    labels_on_nodes = {}
    for index, node in enumerate(nodes, start=1):
        labels = {key: f"{value}{index}" for key, value in node_labels.items()}
        node_resource = ResourceEditor(patches={node: {"metadata": {"labels": labels}}})
        node_resource.update(backup_resources=True)
        node_resources.append(node_resource)
        labels_on_nodes[node.name] = labels
    return node_resources, labels_on_nodes
