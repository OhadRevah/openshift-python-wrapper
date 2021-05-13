from tests.install_upgrade_operators.utils import (
    get_hyperconverged_cdi,
    get_hyperconverged_kubevirt,
)


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
