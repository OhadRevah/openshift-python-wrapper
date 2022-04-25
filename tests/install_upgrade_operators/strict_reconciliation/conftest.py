import importlib
import logging
import pkgutil

import pytest
from ocp_resources.configmap import ConfigMap
from ocp_resources.network_addons_config import NetworkAddonsConfig

from tests.install_upgrade_operators.strict_reconciliation.constants import (
    CUSTOM_HCO_CR_SPEC,
    KV_CR_FEATUREGATES_HCO_CR_DEFAULTS,
)
from tests.install_upgrade_operators.utils import wait_for_stabilize
from utilities.constants import TIMEOUT_10MIN
from utilities.hco import get_hco_spec
from utilities.infra import (
    DEFAULT_RESOURCE_CONDITIONS,
    update_custom_resource,
    wait_for_consistent_resource_conditions,
)


LOGGER = logging.getLogger(__name__)
DISABLED_KUBEVIRT_FEATUREGATES_IN_SNO = ["LiveMigration", "SRIOVLiveMigration"]


@pytest.fixture()
def deleted_stanza_on_hco_cr(
    request, hyperconverged_resource_scope_function, admin_client, hco_namespace
):
    # using retry logic to avoid failing due to ConflictError
    # raised by the validating webhook due to lately propagated side effects
    # of the previous change
    with update_custom_resource(
        patch={hyperconverged_resource_scope_function: request.param["rpatch"]},
        action="replace",
    ):
        yield
    wait_for_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture()
def hco_cr_custom_values(
    hyperconverged_resource_scope_function, admin_client, hco_namespace
):
    """
    This fixture updates HCO CR with custom values for spec.CertConfig, spec.liveMigrationConfig and
    spec.featureGates and cleans those up at the end.
    Note: This is needed for tests that modifies such fields to default values

    Args:
        hyperconverged_resource_scope_function (HyperConverged): HCO CR

    """
    with update_custom_resource(
        patch={hyperconverged_resource_scope_function: CUSTOM_HCO_CR_SPEC.copy()},
    ):
        yield
    wait_for_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture()
def updated_cdi_cr(request, cdi_resource, admin_client, hco_namespace):
    """
    Attempts to update cdi, however, since these changes get reconciled to values propagated by hco cr, we don't need
    to restore these.
    """
    with update_custom_resource(patch={cdi_resource: request.param["patch"]}):
        yield
    wait_for_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture()
def updated_cnao_cr(request, cnao_resource, admin_client, hco_namespace):
    """
    Attempts to update cnao, however, since these changes get reconciled to values propagated by hco cr, we don't need
    to restore these.
    """
    with update_custom_resource(patch={cnao_resource: request.param["patch"]}):
        yield
    wait_for_consistent_resource_conditions(
        dynamic_client=admin_client,
        namespace=hco_namespace,
        expected_conditions=DEFAULT_RESOURCE_CONDITIONS,
        resource_kind=NetworkAddonsConfig,
        condition_key1="type",
        condition_key2="status",
        total_timeout=TIMEOUT_10MIN,
        polling_interval=5,
        consecutive_checks_count=3,
    )
    wait_for_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture()
def updated_kv_with_feature_gates(
    request, admin_client, hco_namespace, kubevirt_resource
):
    kv_dict = kubevirt_resource.instance.to_dict()
    fgs = kv_dict["spec"]["configuration"]["developerConfiguration"][
        "featureGates"
    ].copy()
    fgs.extend(request.param)

    hco_cr_actual_featuregates = get_hco_spec(
        admin_client=admin_client, hco_namespace=hco_namespace
    )["featureGates"]

    assert all(
        KV_CR_FEATUREGATES_HCO_CR_DEFAULTS[f] == v
        for f, v in hco_cr_actual_featuregates.items()
    ), "KubeVirt featuregates values are not as expected before testing"

    with update_custom_resource(
        patch={
            kubevirt_resource: {
                "spec": {
                    "configuration": {"developerConfiguration": {"featureGates": fgs}}
                }
            }
        },
    ):
        yield
    wait_for_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture()
def updated_cdi_with_feature_gates(request, cdi_resource, admin_client, hco_namespace):
    cdi_dict = cdi_resource.instance.to_dict()
    fgs = cdi_dict["spec"]["config"]["featureGates"].copy()
    fgs.extend(request.param)
    with update_custom_resource(
        patch={cdi_resource: {"spec": {"config": {"featureGates": fgs}}}},
    ):
        yield
    wait_for_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture()
def hco_with_non_default_feature_gates(
    request,
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_function,
):
    new_fgs = request.param["fgs"]
    hco_fgs = hyperconverged_resource_scope_function.instance.to_dict()["spec"][
        "featureGates"
    ]

    for fg in new_fgs:
        hco_fgs[fg] = True
    with update_custom_resource(
        patch={
            hyperconverged_resource_scope_function: {"spec": {"featureGates": hco_fgs}}
        },
    ):
        wait_for_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)
        yield
    wait_for_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture()
def cr_func_map(
    hco_spec,
    kubevirt_hyperconverged_spec_scope_function,
    cdi_spec,
    network_addons_config_scope_session,
):
    yield {
        "hco": hco_spec,
        "kubevirt": kubevirt_hyperconverged_spec_scope_function,
        "cdi": cdi_spec,
        "cnao": network_addons_config_scope_session.instance.to_dict(),
    }


@pytest.fixture()
def updated_delete_resource(
    request,
    admin_client,
    hco_namespace,
):
    cr = request.param["resource_func"](
        admin_client=admin_client, hco_namespace=hco_namespace
    )
    with update_custom_resource(patch={cr: request.param["rpatch"]}, action="replace"):
        wait_for_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)
        yield
    wait_for_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture
def kubevirt_storage_class_defaults_configmap_dict(admin_client, hco_namespace):
    yield list(
        ConfigMap.get(
            dyn_client=admin_client,
            name="kubevirt-storage-class-defaults",
            namespace=hco_namespace.name,
        )
    )[0].instance.to_dict()


@pytest.fixture(scope="module")
def ocp_resources_submodule_list():
    """
    Gets the list of submodules in ocp_resources. This list is needed to make get and patch call to the right resource

    """
    path = importlib.util.find_spec("ocp_resources").submodule_search_locations
    list_submodules = [module.name for module in pkgutil.iter_modules(path)]
    LOGGER.info(f"list of modules: {list_submodules}")
    return list_submodules


@pytest.fixture(scope="module")
def related_objects(hyperconverged_resource_scope_module):
    """
    Gets HCO.status.relatedObjects list
    """
    return hyperconverged_resource_scope_module.instance.status.relatedObjects


@pytest.fixture(scope="session")
def default_feature_gates_scope_session(kubevirt_resource_scope_session):
    return (
        kubevirt_resource_scope_session.instance.spec.configuration.developerConfiguration.featureGates
    )
