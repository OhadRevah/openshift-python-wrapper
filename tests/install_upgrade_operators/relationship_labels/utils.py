import json
import logging

from tests.install_upgrade_operators.relationship_labels.constants import (
    ALL_LABEL_KEYS,
    CLUSTER_SCOPE_RESOURCES,
    DEPLOYMENTS,
    EXPECTED_COMPONENT_LABELS_DICT_MAP,
    VERSION_LABEL_KEY,
)


LOGGER = logging.getLogger(__name__)


def verify_labels_in_hco_components(admin_client, hco_namespace):
    """
    Verify that the HCO components have the expected labels values, e.g. 'app.kubernetes.io/component': 'compute'
    and asserts upon mismatch

    Args:
        admin_client (DynamicClient): DynamicClient object
        hco_namespace (Namespace): Namespace object

    Raises:
        AssertionError: raised when there is content in the mismatch dict, containing comparison results of the
            components labels between expected and actual
    """
    LOGGER.info("Verifying labels in HCO components")
    mismatch_results_dict = {}
    for (
        component_kind,
        component_data,
    ) in EXPECTED_COMPONENT_LABELS_DICT_MAP.items():
        for component_name, component_kind_data in component_data.items():
            namespace = component_kind_data.get("namespace", hco_namespace.name)
            kwargs = {"client": admin_client, "name": component_name}
            if component_kind.kind not in CLUSTER_SCOPE_RESOURCES:
                kwargs["namespace"] = namespace
            actual_resource_labels = component_kind(**kwargs).instance.metadata.labels
            comparison_result = (
                compare_expected_vs_actual_labels_and_values_get_mismatches(
                    actual_labels=actual_resource_labels,
                    expected_labels=component_kind_data["expected_labels"],
                )
            )
            if comparison_result:
                if component_kind.kind not in mismatch_results_dict:
                    mismatch_results_dict[component_kind.kind] = {}
                mismatch_results_dict[component_kind.kind][
                    component_name
                ] = comparison_result
    assert (
        not mismatch_results_dict
    ), f"Found mismatch in label values: mismatch_results={json.dumps(mismatch_results_dict, indent=4)}"


def get_pods_labels_for_deployment(
    deployment_name, pod_name_labels_managed_by_olm_dict
):
    """
    Gets pod labels of the provided deployment

    Args:
        deployment_name (str): name of the deployment in question
        pod_name_labels_managed_by_olm_dict (dict): a dict with pod name as key and expected labels (and their values)
            as value

    Returns:
        dict: labels and their corresponding values for a given deployment pods, e.g.:
            {'cdi-operator-6db8cd68b4-t8j82': {'app.kubernetes.io/component': 'storage', ...}, ...}
    """
    actual_pods_resource_labels = {}
    for pod_name, pod_labels_dict in pod_name_labels_managed_by_olm_dict.items():
        for label_key, label_value in pod_labels_dict.items():
            if pod_name.startswith(deployment_name):
                actual_pods_resource_labels.setdefault(pod_name, {})[
                    label_key
                ] = label_value
    return actual_pods_resource_labels


def verify_labels_values_in_olm_deployments(pod_name_labels_managed_by_olm_dict):
    """
    Verify that the Deployments pods have the expected labels values, e.g. 'app.kubernetes.io/managed-by': 'olm'

    Args:
        pod_name_labels_managed_by_olm_dict (dict): dict containing pod name as key and its labels as value

    Raises:
        AssertionError: raised when mismatch in the labels values are found, e.g.:
            {"cdi-operator": [{"app.kubernetes.io/managed-by": {"expected": "olm", "actual": "no_olm"}}]}
    """
    LOGGER.info("Verifying labels' values in deployments")
    mismatch_results_dict = {}
    for deployment_name, expected_deployment_labels in DEPLOYMENTS.items():
        actual_resource_labels = get_pods_labels_for_deployment(
            deployment_name=deployment_name,
            pod_name_labels_managed_by_olm_dict=pod_name_labels_managed_by_olm_dict,
        )
        for pod_result in actual_resource_labels.values():
            comparison_result = (
                compare_expected_vs_actual_labels_and_values_get_mismatches(
                    actual_labels=pod_result,
                    expected_labels=expected_deployment_labels,
                )
            )
            if comparison_result:
                mismatch_results_dict.setdefault(deployment_name, []).append(
                    comparison_result
                )
    assert (
        not mismatch_results_dict
    ), f"Found mismatch in label values: mismatch_results={json.dumps(mismatch_results_dict, indent=4)}"


def verify_no_missing_labels_in_olm_deployments(pod_name_labels_managed_by_olm_dict):
    """
    Verify that the Deployments pods have all the expected labels

    Args:
        pod_name_labels_managed_by_olm_dict (dict): dict containing pod name as key and its labels as value

    Raises:
        AssertionError: raised when there are missing labels in the actual deployments
    """
    LOGGER.info("Verifying labels in deployments")
    mismatch_results_dict = {}
    for deployment_name, expected_deployment_labels in DEPLOYMENTS.items():
        actual_resource_labels = get_pods_labels_for_deployment(
            deployment_name=deployment_name,
            pod_name_labels_managed_by_olm_dict=pod_name_labels_managed_by_olm_dict,
        )
        for pod_result in actual_resource_labels.values():
            missing_labels = [
                expected_label_key
                for expected_label_key in ALL_LABEL_KEYS
                if expected_label_key not in pod_result
            ]
            if missing_labels:
                mismatch_results_dict.setdefault(deployment_name, []).append(
                    missing_labels
                )
    assert (
        not mismatch_results_dict
    ), f"Found missing labels: missing_labels={json.dumps(mismatch_results_dict, indent=4)}"


def compare_expected_vs_actual_labels_and_values_get_mismatches(
    actual_labels,
    expected_labels,
):
    """
    Compare label actual value against the expected value and update the mismatch results dict

    Args:
        actual_labels (dict): actual labels-values pairs from the cluster
        expected_labels (dict): expected labels-values pairs

    Returns:
        dict: dict with mismatched label values
    """
    return {
        expected_label_key: {
            "expected": expected_label_value,
            "actual": actual_labels[expected_label_key],
        }
        for expected_label_key, expected_label_value in expected_labels.items()
        if compare_label_key(
            expected=expected_label_value,
            actual=actual_labels[expected_label_key],
            label_key=expected_label_key,
        )
    }


def compare_label_key(expected, actual, label_key):
    # in nightly/pre-release, the csv version string includes the build number
    if label_key == VERSION_LABEL_KEY:
        expected = expected.split("-")[0]
    return expected != actual
