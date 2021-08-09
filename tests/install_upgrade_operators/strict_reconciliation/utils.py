import logging

from dictdiffer import diff
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler

from tests.install_upgrade_operators.strict_reconciliation import constants
from tests.install_upgrade_operators.utils import (
    get_function_name,
    get_hco_spec,
    get_hyperconverged_cdi,
    get_hyperconverged_kubevirt,
    get_network_addon_config,
)


LOGGER = logging.getLogger(__name__)


def verify_spec(expected_spec, get_spec_func):
    samplers = TimeoutSampler(
        wait_timeout=60,
        sleep=5,
        exceptions=AssertionError,
        func=lambda: list(diff(expected_spec, get_spec_func())),
    )
    diff_result = None
    try:
        for diff_result in samplers:
            if not diff_result:
                return True

    except TimeoutExpiredError:
        LOGGER.error(
            f"{get_function_name(function_name=get_spec_func)}: Timed out waiting for CR with expected spec."
            f" spec: '{expected_spec}' diff:'{diff_result}'"
        )
        raise


def verify_specs(
    admin_client,
    hco_namespace,
    hco_spec,
    kubevirt_hyperconverged_spec_scope_function,
    cdi_spec,
    cnao_spec,
):
    verify_spec(
        expected_spec=hco_spec,
        get_spec_func=lambda: get_hco_spec(
            admin_client=admin_client, hco_namespace=hco_namespace
        ),
    )
    verify_spec(
        expected_spec=kubevirt_hyperconverged_spec_scope_function,
        get_spec_func=lambda: get_hyperconverged_kubevirt(
            admin_client=admin_client, hco_namespace=hco_namespace
        )
        .instance.to_dict()
        .get("spec"),
    )
    verify_spec(
        expected_spec=cdi_spec,
        get_spec_func=lambda: get_hyperconverged_cdi(
            admin_client=admin_client, hco_namespace=hco_namespace
        )
        .instance.to_dict()
        .get("spec"),
    )
    verify_spec(
        expected_spec=cnao_spec,
        get_spec_func=lambda: get_network_addon_config(admin_client=admin_client)
        .instance.to_dict()
        .get("spec"),
    )
    # when none of the functions above raise TimeoutExpiredError
    return True


def validate_featuregates_not_in_kv_cr(
    admin_client, hco_namespace, feature_gates_under_test
):
    kv = get_hyperconverged_kubevirt(
        admin_client=admin_client, hco_namespace=hco_namespace
    ).instance.to_dict()

    kv_fgs = kv["spec"]["configuration"]["developerConfiguration"]["featureGates"]
    return all(fg not in kv_fgs for fg in feature_gates_under_test)


def validate_featuregates_not_in_cdi_cr(
    admin_client, hco_namespace, feature_gates_under_test
):
    """
    Validates that all expected featuregates are present in cdi CR

    Args:
        admin_client(DynamicClient): DynamicClient object
        hco_namespace (Namespace): Namespace object
        feature_gates_under_test (list): list of featuregates to compare against current list of featuregates
    returns:
        bool: returns True or False
    """
    cdi = get_hyperconverged_cdi(
        admin_client=admin_client, hco_namespace=hco_namespace
    ).instance.to_dict()

    cdi_fgs = cdi["spec"]["config"]["featureGates"]
    return all(fg not in cdi_fgs for fg in feature_gates_under_test)


def compare_expected_with_cr(expected, actual):
    # filtering out the "add" verb - it contains additional keys that do not exist in the expected dict, and are
    # other fields in the spec that are not tested and irrelevant to this test
    return list(
        filter(
            lambda diff_result_item: diff_result_item[0] != "add",
            list(diff(expected, actual)),
        )
    )


def expected_certconfig_stanza():
    return {
        "ca": {
            "duration": constants.CERTC_DEFAULT_48H,
            "renewBefore": constants.CERTC_DEFAULT_24H,
        },
        "server": {
            "duration": constants.CERTC_DEFAULT_24H,
            "renewBefore": constants.CERTC_DEFAULT_12H,
        },
    }


def remove_items_from_hardcoded_feature_gates(hardcoded_featuregate_to_remove):
    return list(
        set(constants.EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES)
        - set(hardcoded_featuregate_to_remove)
    )


def create_rpatch_dict(subset_feature_gates_list_to_remove):
    return {
        "spec": {
            "configuration": {
                "developerConfiguration": {
                    "featureGates": remove_items_from_hardcoded_feature_gates(
                        hardcoded_featuregate_to_remove=subset_feature_gates_list_to_remove
                    ),
                }
            }
        }
    }


def validate_featuregates_in_kv_cr(
    admin_client, hco_namespace, feature_gates_under_test
):
    """
    Validates that all expected featuregates are present in kubevirt CR

    Args:
        admin_client(DynamicClient): DynamicClient object
        hco_namespace (Namespace): Namespace object
        feature_gates_under_test (list): list of featuregates to compare against current list of featuregates
    returns:
        bool: returns True or False
    """
    kv = get_hyperconverged_kubevirt(
        admin_client=admin_client, hco_namespace=hco_namespace
    ).instance.to_dict()

    kv_fgs = kv["spec"]["configuration"]["developerConfiguration"]["featureGates"]
    return all(fg in kv_fgs for fg in feature_gates_under_test)


def wait_for_fg_update(admin_client, hco_namespace, expected_fg, validate_func):
    """
    Waits for featuregate updates to get propagated

    Args:
        admin_client(DynamicClient): DynamicClient object
        hco_namespace (Namespace): Namespace object
        expected_fg (list): list of featuregates to compare against current list of featuregates
        validate_func (function): validate function to be used for comparision
    """
    samples = TimeoutSampler(
        wait_timeout=30,
        sleep=1,
        func=validate_func,
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        feature_gates_under_test=expected_fg,
    )
    try:
        for sample in samples:
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"Timeout validating featureGates field values using "
            f"{get_function_name(function_name=validate_func)}: comparing with fg: {expected_fg}"
        )
        raise
