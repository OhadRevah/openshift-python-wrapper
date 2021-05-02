import logging

import pytest
from ocp_resources.resource import ResourceEditor

from tests.install_upgrade_operators.strict_reconciliation.constants import (
    CUSTOM_HCO_CR_SPEC,
)
from tests.install_upgrade_operators.strict_reconciliation.utils import get_hco_spec
from utilities.hco import (
    modify_hco_cr,
    replace_backup_hco_cr_modification,
    restore_hco_cr_modification,
)


LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def deleted_stanza_on_hco_cr(
    request, hyperconverged_resource_scope_function, admin_client, hco_namespace
):
    # using retry logic to avoid failing due to ConflictError
    # raised by the validating webhook due to lately propagated side effects
    # of the previous change
    backup_data = replace_backup_hco_cr_modification(
        rpatch=request.param,
        admin_client=admin_client,
        hco_namespace=hco_namespace,
    )
    yield
    restore_hco_cr_modification(
        admin_client=admin_client, hco_namespace=hco_namespace, backup_data=backup_data
    )


@pytest.fixture()
def hco_spec(admin_client, hco_namespace):
    return get_hco_spec(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture()
def hco_cr_custom_values(
    hyperconverged_resource_scope_function,
):
    """
    This fixture updates HCO CR with custom values for spec.CertConfig, spec.liveMigrationConfig and
    spec.featureGates and cleans those up at the end.
    Note: This is needed for tests that modifies such fields to default values

    Args:
        hyperconverged_resource_scope_function (HyperConverged): HCO CR

    """
    modify_hco_cr(
        patch=CUSTOM_HCO_CR_SPEC.copy(),
        hco=hyperconverged_resource_scope_function,
    )
    yield
    modify_hco_cr(
        patch={
            "spec": {"liveMigrationConfig": {}, "certConfig": {}, "featureGates": {}}
        },
        hco=hyperconverged_resource_scope_function,
    )


@pytest.fixture()
def update_hco_cr(request, hyperconverged_resource_scope_function):
    """
    This fixture updates HCO CR with values specified via request.param

    Args:
        hyperconverged_resource_scope_function (HyperConverged): HCO CR

    """
    modify_hco_cr(
        patch=request.param["patch"], hco=hyperconverged_resource_scope_function
    )
    yield


@pytest.fixture()
def update_cdi_cr(request, cdi_resource):
    patch = request.param["patch"]
    with ResourceEditor(patches={cdi_resource: patch}):
        yield


@pytest.fixture()
def update_kubevirt_cr(request, kubevirt_resource):
    patch = request.param["patch"]

    with ResourceEditor(patches={kubevirt_resource: patch}):
        yield


@pytest.fixture()
def update_cnao_cr(request, cnao_resource):
    patch = request.param["patch"]

    with ResourceEditor(patches={cnao_resource: patch}):
        yield


@pytest.fixture()
def updated_kv_with_feature_gates(request, kubevirt_resource):
    requested_fgs = request.param
    kv_dict = kubevirt_resource.instance.to_dict()
    fgs = kv_dict["spec"]["configuration"]["developerConfiguration"][
        "featureGates"
    ].copy()
    fgs.extend(requested_fgs)

    with ResourceEditor(
        patches={
            kubevirt_resource: {
                "spec": {
                    "configuration": {"developerConfiguration": {"featureGates": fgs}}
                }
            }
        },
    ):
        yield


@pytest.fixture()
def updated_cdi_with_feature_gates(request, cdi_resource):
    requested_fgs = request.param
    cdi_dict = cdi_resource.instance.to_dict()
    fgs = cdi_dict["spec"]["config"]["featureGates"].copy()
    fgs.extend(requested_fgs)

    with ResourceEditor(
        patches={cdi_resource: {"spec": {"config": {"featureGates": fgs}}}},
    ):
        yield


@pytest.fixture()
def hco_with_non_default_feature_gates(request, hyperconverged_resource_scope_function):
    new_fgs = request.param

    hco_fgs = hyperconverged_resource_scope_function.instance.to_dict()["spec"][
        "featureGates"
    ]
    for fg in new_fgs:
        hco_fgs[fg] = True

    with ResourceEditor(
        patches={
            hyperconverged_resource_scope_function: {"spec": {"featureGates": hco_fgs}}
        }
    ):
        yield


@pytest.fixture()
def cr_func_map(
    hyperconverged_resource_scope_function,
    kubevirt_hyperconverged_spec_scope_function,
    cdi_spec,
    network_addons_config,
):
    yield {
        "hco": hyperconverged_resource_scope_function.instance.to_dict()["spec"],
        "kubevirt": kubevirt_hyperconverged_spec_scope_function,
        "cdi": cdi_spec,
        "cnao": network_addons_config.instance.to_dict(),
    }
