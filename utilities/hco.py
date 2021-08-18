import logging

from ocp_resources.daemonset import DaemonSet
from ocp_resources.deployment import Deployment
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.resource import Resource, ResourceEditor
from ocp_resources.storage_class import StorageClass
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from openshift.dynamic.exceptions import ConflictError
from pytest_testconfig import config as py_config

from utilities.constants import TIMEOUT_4MIN, TIMEOUT_10MIN
from utilities.infra import (
    wait_for_consistent_resource_conditions,
    wait_for_pods_running,
)


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


def get_hyperconverged_resource(client, hco_ns_name):
    for hco in HyperConverged.get(
        dyn_client=client,
        namespace=hco_ns_name,
        name=py_config["hco_cr_name"],
    ):
        return hco


def wait_for_hco_conditions(
    admin_client,
    hco_namespace,
    expected_conditions=DEFAULT_HCO_CONDITIONS,
    wait_timeout=TIMEOUT_10MIN,
    sleep=5,
    consecutive_checks_count=1,
    condition_key1="type",
    condition_key2="status",
):
    """
    Checking HCO conditions
    """
    wait_for_consistent_resource_conditions(
        dynamic_client=admin_client,
        hco_namespace=hco_namespace,
        expected_conditions=expected_conditions,
        resource_kind=HyperConverged,
        condition_key1=condition_key1,
        condition_key2=condition_key2,
        total_timeout=wait_timeout,
        polling_interval=sleep,
        consecutive_checks_count=consecutive_checks_count,
    )


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
        patch = {
            "spec": {
                "infra": target_infra or None,
                "workloads": target_workloads or None,
            }
        }
        LOGGER.info(f"Updating HCO with node placement. {patch}")
        editor = ResourceEditor(patches={hco: patch})
        editor.update(backup_resources=False)
        LOGGER.info(
            "Waiting for all HCO conditions to detect that it's back to a stable configuration."
        )
        wait_for_hco_conditions(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            consecutive_checks_count=6,
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
            # We need to skip checking "hostpath-provisioner" daemonset, since it is not managed by HCO CR
            if not ds.name.startswith(StorageClass.Types.HOSTPATH):
                wait_for_ds(ds=ds)
        for dp in Deployment.get(
            dyn_client=admin_client,
            namespace=hco_namespace.name,
        ):
            wait_for_dp(dp=dp)
        wait_for_pods_running(
            admin_client=admin_client,
            namespace=hco_namespace,
            number_of_consecutive_checks=3,
        )
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


def replace_hco_cr(rpatch, admin_client, hco_namespace):
    # fetch hyperconverged_resource each time instead of using a single
    # fixture to be sure to get it with an up to date resourceVersion
    # as needed for action=replace
    hyperconverged_resource = get_hyperconverged_resource(
        client=admin_client, hco_ns_name=hco_namespace.name
    )

    # we have to use action="replace" to send a put to delete existing fields
    # (update, the default, will only update existing fields).
    reseditor = ResourceEditor(
        patches={hyperconverged_resource: rpatch}, action="replace"
    )
    reseditor.update(backup_resources=True)
    return reseditor.backups


def replace_backup_hco_cr_modification(rpatch, admin_client, hco_namespace):
    samples = TimeoutSampler(
        wait_timeout=20,
        sleep=2,
        exceptions_dict={ConflictError: []},
        func=replace_hco_cr,
        rpatch=rpatch,
        admin_client=admin_client,
        hco_namespace=hco_namespace,
    )
    try:
        for sample in samples:
            if sample:
                return sample
    except TimeoutExpiredError:
        LOGGER.error("TimeOut: During HCO Modification")
        raise


def restore_hco_cr_modification(admin_client, hco_namespace, backup_data):
    for backup in backup_data:
        # Backup the HCO CR changes and revert back once teardown happens for class
        samples = TimeoutSampler(
            wait_timeout=20,
            sleep=2,
            exceptions_dict={ConflictError: []},
            func=replace_hco_cr,
            rpatch=backup.instance.to_dict()["spec"],
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )
        try:
            for sample in samples:
                if sample:
                    break
        except TimeoutExpiredError:
            LOGGER.error("Timeout restoring default value in hyperconverged CR.")
            raise


def get_hco_spec(admin_client, hco_namespace):
    return get_hyperconverged_resource(
        client=admin_client, hco_ns_name=hco_namespace.name
    ).instance.to_dict()["spec"]
