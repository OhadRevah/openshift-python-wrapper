import inspect
import logging

from dictdiffer import diff
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler

from tests.install_upgrade_operators.strict_reconciliation import constants
from tests.install_upgrade_operators.utils import (
    get_hyperconverged_cdi,
    get_hyperconverged_kubevirt,
    get_network_addon_config,
)
from utilities.hco import get_hyperconverged_resource


LOGGER = logging.getLogger(__name__)


def get_hco_spec(admin_client, hco_namespace):
    return get_hyperconverged_resource(
        client=admin_client, hco_ns_name=hco_namespace.name
    ).instance.to_dict()["spec"]


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


def get_function_name(function_name):
    """
    Return the text of the source code for a function

    Args:
        function_name (function object): function object

    Returns:
        str: name of the function
    """
    return inspect.getsource(function_name).split("(")[0].split(" ")[-1]


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
    admin_client, hco_namespace, feature_gate_under_test
):
    cdi = get_hyperconverged_cdi(
        admin_client=admin_client, hco_namespace=hco_namespace
    ).instance.to_dict()

    cdi_fgs = cdi["spec"]["config"]["featureGates"]
    return feature_gate_under_test not in cdi_fgs


def assert_specs_values(expected, get_spec_func, keys):
    """
    Asserts that expected values of spec fields

    Args:
        expected (dict): dictionary of values that would be used to update hco cr
        get_spec_func (function): function to fetch current spec dictionary
        keys (list): list of associated keys for a given kind.
    """
    spec_dict = get_spec_func()
    spec = {key: spec_dict[key] for key in keys if key in spec_dict}
    diff_spec = list(
        filter(
            lambda diff_result_item: diff_result_item[0] == "change",
            list(diff(spec, expected)),
        )
    )
    assert not diff_spec, (
        f"For {get_function_name(function_name=get_spec_func)}, expected value: {expected} "
        f"does not match with actual value: {spec}"
    )


def wait_for_spec_change(expected, get_spec_func, keys):
    """
    Waits for spec values to get propagated

    Args:
        expected (dict): dictionary of values that would be used to update hco cr
        get_spec_func (function): function to fetch current spec dictionary
        keys (list): list of associated keys for a given kind.
    """
    samplers = TimeoutSampler(
        wait_timeout=60,
        sleep=5,
        exceptions=AssertionError,
        func=assert_specs_values,
        expected=expected,
        get_spec_func=get_spec_func,
        keys=keys,
    )
    diff_result = None
    try:
        for diff_result in samplers:
            if not diff_result:
                return True

    except TimeoutExpiredError:
        LOGGER.error(
            f"{get_function_name(function_name=get_spec_func)}: Timed out waiting for CR with expected spec."
            f" spec: '{expected}' diff:'{diff_result}'"
        )
        raise


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
