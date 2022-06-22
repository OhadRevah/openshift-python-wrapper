import json
import logging
from contextlib import contextmanager

from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.namespace import Namespace
from ocp_resources.resource import Resource, ResourceEditor
from ocp_resources.storage_class import StorageClass
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from pytest_testconfig import py_config

from utilities.constants import (
    ENABLE_COMMON_BOOT_IMAGE_IMPORT_FEATURE_GATE,
    HCO_SUBSCRIPTION,
    TIMEOUT_2MIN,
    TIMEOUT_4MIN,
    TIMEOUT_10MIN,
    TIMEOUT_30MIN,
)
from utilities.infra import (
    get_admin_client,
    get_csv_by_name,
    get_daemonsets,
    get_deployments,
    get_hyperconverged_resource,
    get_subscription,
    wait_for_consistent_resource_conditions,
    wait_for_pods_running,
)
from utilities.ssp import (
    wait_for_at_least_one_auto_update_data_import_cron,
    wait_for_deleted_data_import_crons,
    wait_for_ssp_conditions,
)


LOGGER = logging.getLogger(__name__)

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
HCO_JSONPATCH_ANNOTATION_COMPONENT_DICT = {
    "kubevirt": {
        "api_group_prefix": "kubevirt",
        "config": "configuration/",
    },
    "cdi": {
        "api_group_prefix": "containerizeddataimporter",
        "config": "config/",
    },
    "cnao": {
        "api_group_prefix": "networkaddonsconfigs",
    },
}


class ResourceEditorValidateHCOReconcile(ResourceEditor):
    def __init__(
        self, hco_namespace="openshift-cnv", consecutive_checks_count=3, **kwargs
    ):
        super().__init__(**kwargs)
        self._consecutive_checks_count = consecutive_checks_count
        self.hco_namespace = hco_namespace

    def restore(self):
        super().restore()
        admin_client = get_admin_client()
        wait_for_hco_conditions(
            admin_client=admin_client,
            hco_namespace=get_hco_namespace(
                admin_client=admin_client, namespace=self.hco_namespace
            ),
            consecutive_checks_count=self._consecutive_checks_count,
        )


@contextmanager
def update_custom_resource(patch, action="update"):
    """Update any CR with given values

    Args:
        patch (dict): dictionary of values that would be used to update a cr. This dict should include the resource
        as the base key
        action (str): type of action to be performed. e.g. "update", "replace" etc.

    Yields:
        dict: {<Resource object>: <backup_as_dict>} or True in case no backup option is selected
    """
    with ResourceEditorValidateHCOReconcile(
        patches=patch,
        action=action,
    ) as edited_source:
        yield edited_source


def wait_for_hco_conditions(
    admin_client,
    hco_namespace,
    expected_conditions=None,
    wait_timeout=TIMEOUT_10MIN,
    sleep=5,
    consecutive_checks_count=3,
    condition_key1="type",
    condition_key2="status",
):
    """
    Checking HCO conditions
    """
    wait_for_consistent_resource_conditions(
        dynamic_client=admin_client,
        namespace=hco_namespace.name,
        expected_conditions=expected_conditions or DEFAULT_HCO_CONDITIONS,
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
        wait_for_hco_post_update_stable_state(
            admin_client=admin_client, hco_namespace=hco_namespace
        )
    else:
        LOGGER.info("No actual changes to node placement configuration, skipping")


def wait_for_hco_post_update_stable_state(admin_client, hco_namespace):
    """
    Waits for hco to reach stable state post hco update

    Args:
        admin_client (DynamicClient): Dynamic client object
        hco_namespace (Namespace): Namespace object
    """
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
    for ds in get_daemonsets(admin_client=admin_client, namespace=hco_namespace.name):
        # We need to skip checking "hostpath-provisioner" daemonset, since it is not managed by HCO CR
        if not ds.name.startswith(StorageClass.Types.HOSTPATH):
            wait_for_ds(ds=ds)
    for deployment in get_deployments(
        admin_client=admin_client,
        namespace=hco_namespace.name,
    ):
        wait_for_dp(dp=deployment)
    wait_for_pods_running(
        admin_client=admin_client,
        namespace=hco_namespace,
        number_of_consecutive_checks=3,
    )


def add_labels_to_nodes(nodes, node_labels):
    """
    Adds given labels to a list of nodes

    Args:
        nodes (list): list of nodes
        node_labels (dict): dictionary of labels to be applied

    Returns:
        dictionary with information on labels applied for all the nodes and associated resource editors for the same

    """
    node_resources = {}
    for index, node in enumerate(nodes, start=1):
        labels = {key: f"{value}{index}" for key, value in node_labels.items()}
        node_resource = ResourceEditor(patches={node: {"metadata": {"labels": labels}}})
        node_resource.update(backup_resources=True)
        node_resources[node_resource] = {"node": node.name, "labels": labels}
    return node_resources


def get_hco_spec(admin_client, hco_namespace):
    return get_hyperconverged_resource(
        client=admin_client, hco_ns_name=hco_namespace.name
    ).instance.to_dict()["spec"]


def get_installed_hco_csv(admin_client, hco_namespace):
    cnv_subscription = get_subscription(
        admin_client=admin_client,
        namespace=hco_namespace.name,
        subscription_name=py_config["hco_subscription"] or HCO_SUBSCRIPTION,
    )
    return get_csv_by_name(
        csv_name=cnv_subscription.instance.status.installedCSV,
        admin_client=admin_client,
        namespace=hco_namespace.name,
    )


def get_hco_version(client, hco_ns_name):
    """
    Get current hco version

    Args:
        client (DynamicClient): Dynamic client object
        hco_ns_name (str): hco namespace name

    Returns:
        str: hyperconverged operator version
    """
    return (
        get_hyperconverged_resource(client=client, hco_ns_name=hco_ns_name)
        .instance.status.versions[0]
        .version
    )


def wait_for_hco_version(client, hco_ns_name, cnv_version):
    """
    Wait for hco version to get updated.

    Args:
        client (DynamicClient): Dynamic client object
        hco_ns_name (str): hco namespace name
        cnv_version (str): cnv version string that should match with current cnv version

    Returns:
        str: hco version string

    Raises:
        TimeoutExpiredError: if hco resource is not updated with expected version string
    """
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_30MIN,
        sleep=5,
        func=get_hco_version,
        client=client,
        hco_ns_name=hco_ns_name,
    )
    sample = None
    try:
        for sample in samples:
            if sample and sample == cnv_version:
                LOGGER.info(f"HCO version updated to {cnv_version}")
                return sample
    except TimeoutExpiredError:
        LOGGER.error(
            f"Expected HCO version: {cnv_version}, actual hco version: {sample}"
        )
        raise


def disable_common_boot_image_import_feature_gate(
    admin_client,
    hco_resource,
    golden_images_namespace,
    golden_images_data_import_crons,
):
    if hco_resource.instance.spec.featureGates[
        ENABLE_COMMON_BOOT_IMAGE_IMPORT_FEATURE_GATE
    ]:
        update_common_boot_image_import_feature_gate(
            hco_resource=hco_resource,
            enable_feature_gate=False,
        )
        wait_for_deleted_data_import_crons(
            data_import_crons=golden_images_data_import_crons
        )
        yield
        # Always enable enableCommonBootImageImport feature gate after test execution
        enable_common_boot_image_import_feature_gate_wait_for_data_import_cron(
            hco_resource=hco_resource,
            admin_client=admin_client,
            namespace=golden_images_namespace,
        )
    else:
        yield


def enable_common_boot_image_import_feature_gate_wait_for_data_import_cron(
    hco_resource, admin_client, namespace
):
    hco_namespace = Namespace(name=hco_resource.namespace)
    update_common_boot_image_import_feature_gate(
        hco_resource=hco_resource,
        enable_feature_gate=True,
    )
    wait_for_at_least_one_auto_update_data_import_cron(
        admin_client=admin_client, namespace=namespace
    )
    wait_for_ssp_conditions(admin_client=admin_client, hco_namespace=hco_namespace)
    wait_for_hco_conditions(admin_client=admin_client, hco_namespace=hco_namespace)


def update_common_boot_image_import_feature_gate(hco_resource, enable_feature_gate):
    def _wait_for_feature_gate_update(_hco_resource, _enable_feature_gate):
        LOGGER.info(
            f"Wait for HCO {ENABLE_COMMON_BOOT_IMAGE_IMPORT_FEATURE_GATE} "
            f"feature gate to be set to {_enable_feature_gate}."
        )
        try:
            for sample in TimeoutSampler(
                wait_timeout=TIMEOUT_2MIN,
                sleep=5,
                func=lambda: _hco_resource.instance.spec.featureGates[
                    ENABLE_COMMON_BOOT_IMAGE_IMPORT_FEATURE_GATE
                ]
                == _enable_feature_gate,
            ):
                if sample:
                    return
        except TimeoutExpiredError:
            LOGGER.error(
                f"{ENABLE_COMMON_BOOT_IMAGE_IMPORT_FEATURE_GATE} was not updated to {_enable_feature_gate}"
            )
            raise

    editor = ResourceEditor(
        patches={
            hco_resource: {
                "spec": {
                    "featureGates": {
                        ENABLE_COMMON_BOOT_IMAGE_IMPORT_FEATURE_GATE: enable_feature_gate
                    }
                }
            }
        }
    )
    editor.update(backup_resources=True)
    _wait_for_feature_gate_update(
        _hco_resource=hco_resource, _enable_feature_gate=enable_feature_gate
    )


def get_hco_namespace(admin_client, namespace="openshift-cnv"):
    return list(
        Namespace.get(
            dyn_client=admin_client,
            field_selector=f"metadata.name=={namespace}",
        )
    )[0]


def hco_cr_jsonpatch_annotations_dict(component, path, value, op="add"):
    # https://github.com/kubevirt/hyperconverged-cluster-operator/blob/master/docs/cluster-configuration.md#jsonpatch-annotations
    component_dict = HCO_JSONPATCH_ANNOTATION_COMPONENT_DICT[component]
    return {
        "metadata": {
            "annotations": {
                f"{component_dict['api_group_prefix']}.{Resource.ApiGroup.KUBEVIRT_IO}/jsonpatch": json.dumps(
                    [
                        {
                            "op": op,
                            "path": f"/spec/{component_dict.get('config', '')}{path}",
                            "value": value,
                        }
                    ]
                )
            }
        }
    }
