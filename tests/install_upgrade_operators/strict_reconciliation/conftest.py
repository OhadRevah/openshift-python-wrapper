import logging

import pytest
from ocp_resources.configmap import ConfigMap
from ocp_resources.resource import ResourceEditor
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from openshift.dynamic.exceptions import ConflictError

from tests.install_upgrade_operators.strict_reconciliation.constants import (
    CUSTOM_HCO_CR_SPEC,
    KV_CR_FEATUREGATES_HCO_CR_DEFAULTS,
)
from tests.install_upgrade_operators.utils import wait_for_stabilize
from utilities.hco import (
    get_hco_spec,
    replace_backup_hco_cr_modification,
    restore_hco_cr_modification,
)
from utilities.infra import update_custom_resource


LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def deleted_stanza_on_hco_cr(
    request, hyperconverged_resource_scope_function, admin_client, hco_namespace
):
    # using retry logic to avoid failing due to ConflictError
    # raised by the validating webhook due to lately propagated side effects
    # of the previous change
    backup_data = replace_backup_hco_cr_modification(
        rpatch=request.param["rpatch"],
        admin_client=admin_client,
        hco_namespace=hco_namespace,
    )
    yield
    restore_hco_cr_modification(
        admin_client=admin_client, hco_namespace=hco_namespace, backup_data=backup_data
    )


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
    with update_custom_resource(
        patch={hyperconverged_resource_scope_function: CUSTOM_HCO_CR_SPEC.copy()},
    ):
        yield


@pytest.fixture()
def updated_cdi_cr(request, cdi_resource):
    """
    Attempts to update cdi, however, since these changes get reconciled to values propagated by hco cr, we don't need
    to restore these.
    """
    patch = request.param["patch"]
    with update_custom_resource(patch={cdi_resource: patch}):
        yield


@pytest.fixture()
def updated_cnao_cr(request, cnao_resource):
    """
    Attempts to update cnao, however, since these changes get reconciled to values propagated by hco cr, we don't need
    to restore these.
    """
    patch = request.param["patch"]
    with update_custom_resource(patch={cnao_resource: patch}):
        yield


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


@pytest.fixture()
def updated_cdi_with_feature_gates(request, cdi_resource):
    cdi_dict = cdi_resource.instance.to_dict()
    fgs = cdi_dict["spec"]["config"]["featureGates"].copy()
    fgs.extend(request.param)
    with update_custom_resource(
        patch={cdi_resource: {"spec": {"config": {"featureGates": fgs}}}},
    ):
        yield


@pytest.fixture()
def hco_with_non_default_feature_gates(
    request, admin_client, hco_namespace, hyperconverged_resource_scope_function
):
    wait_for_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)
    new_fgs = request.param["fgs"]
    hco_fgs = hyperconverged_resource_scope_function.instance.to_dict()["spec"][
        "featureGates"
    ]
    assert all(
        KV_CR_FEATUREGATES_HCO_CR_DEFAULTS[f] == v for f, v in hco_fgs.items()
    ), (
        f"HCO featuregates values before testing: {hco_fgs} are not as expected before testing"
        f" {KV_CR_FEATUREGATES_HCO_CR_DEFAULTS}"
    )
    for fg in new_fgs:
        hco_fgs[fg] = True
    with update_custom_resource(
        patch={
            hyperconverged_resource_scope_function: {"spec": {"featureGates": hco_fgs}}
        },
    ):
        wait_for_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)
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


@pytest.fixture()
def updated_delete_resource(
    request,
    admin_client,
    hco_namespace,
):
    backup_data = replace_backup_cr_modification(
        rpatch=request.param["rpatch"],
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        cr_func=request.param["resource_func"],
    )
    wait_for_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)
    yield
    restore_cr_modification(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        backup_data=backup_data,
        cr_func=request.param["resource_func"],
    )
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


@pytest.fixture
def v2v_vmware_configmap_dict(admin_client, hco_namespace):
    yield list(
        ConfigMap.get(
            dyn_client=admin_client,
            name="v2v-vmware",
            namespace=hco_namespace.name,
        )
    )[0].instance.to_dict()


def replace_cr(rpatch, admin_client, hco_namespace, cr_func, action="replace"):
    # fetch the CR according to the cr_func each time instead of using a single
    # fixture to be sure to get it with an up to date resourceVersion
    # as needed for action=replace
    cr = cr_func(admin_client=admin_client, hco_namespace=hco_namespace)

    # we have to use action="replace" to send a put to delete existing fields
    # (update, the default, will only update existing fields).
    reseditor = ResourceEditor(patches={cr: rpatch}, action=action)
    reseditor.update(backup_resources=True)
    return reseditor.backups


def replace_backup_cr_modification(rpatch, admin_client, hco_namespace, cr_func):
    samples = TimeoutSampler(
        wait_timeout=20,
        sleep=2,
        exceptions_dict={ConflictError: []},
        func=replace_cr,
        rpatch=rpatch,
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        cr_func=cr_func,
    )
    try:
        for sample in samples:
            if sample:
                return sample
    except TimeoutExpiredError:
        LOGGER.error(f"Timeout during CR modification: cr={cr_func}")
        raise


def restore_cr_modification(admin_client, hco_namespace, backup_data, cr_func):
    for backup in backup_data:
        # Backup the CR changes and revert back once teardown happens for class
        samples = TimeoutSampler(
            wait_timeout=20,
            sleep=2,
            exceptions_dict={ConflictError: []},
            func=replace_cr,
            rpatch={"spec": backup.instance.to_dict()["spec"]},
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            cr_func=cr_func,
        )
        try:
            for sample in samples:
                if sample:
                    break
        except TimeoutExpiredError:
            LOGGER.error(f"Timeout restoring previous data in CR: cr={backup.name}")
            raise
