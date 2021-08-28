import json

from tests.install_upgrade_operators.relationship_labels.constants import (
    CLUSTER_SCOPE_RESOURCES,
    EXPECTED_COMPONENT_LABELS_DICT_MAP,
)


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
        if expected_label_value != actual_labels[expected_label_key]
    }
