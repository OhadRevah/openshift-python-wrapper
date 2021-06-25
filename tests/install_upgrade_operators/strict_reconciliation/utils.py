import logging

from dictdiffer import diff
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler

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
    try:
        for diff_result in samplers:
            if not diff_result:
                break
            LOGGER.info(
                f"Waiting for CR with expected spec. spec:'{expected_spec}' diff:'{diff_result}'"
            )
    except TimeoutExpiredError:
        LOGGER.error(f"Timeout waiting for CR with expected spec {expected_spec}")
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
    admin_client, hco_namespace, feature_gate_under_test
):
    cdi = get_hyperconverged_cdi(
        admin_client=admin_client, hco_namespace=hco_namespace
    ).instance.to_dict()

    cdi_fgs = cdi["spec"]["config"]["featureGates"]
    return feature_gate_under_test not in cdi_fgs
