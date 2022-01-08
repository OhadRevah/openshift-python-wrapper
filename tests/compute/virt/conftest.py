import pytest
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from pytest_testconfig import py_config

from tests.compute.virt.utils import append_feature_gate_to_hco
from utilities.storage import create_or_update_data_source


@pytest.fixture()
def skip_rwo_default_access_mode():
    if py_config["default_access_mode"] == PersistentVolumeClaim.AccessMode.RWO:
        pytest.skip("Skipping, default storage access mode is RWO")


@pytest.fixture()
def enabled_featuregate_scope_function(
    request,
    hyperconverged_resource_scope_function,
    kubevirt_feature_gates,
    admin_client,
    hco_namespace,
):
    feature_gate = request.param
    kubevirt_feature_gates.append(feature_gate)
    with append_feature_gate_to_hco(
        feature_gate=kubevirt_feature_gates,
        resource=hyperconverged_resource_scope_function,
        client=admin_client,
        namespace=hco_namespace,
    ):
        yield


@pytest.fixture(scope="class")
def golden_image_dv_scope_module_data_source_scope_class(
    admin_client, golden_image_data_volume_scope_module
):
    yield from create_or_update_data_source(
        admin_client=admin_client, dv=golden_image_data_volume_scope_module
    )
