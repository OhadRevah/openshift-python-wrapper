import pytest

from tests.install_upgrade_operators.launcher_updates.constants import (
    CUSTOM_WORKLOAD_STRATEGY_SPEC,
)
from tests.install_upgrade_operators.utils import wait_for_stabilize
from utilities.hco import update_custom_resource


@pytest.fixture()
def updated_workload_strategy_custom_values(
    hyperconverged_resource_scope_function, admin_client, hco_namespace
):
    """
    This fixture updates HCO CR with custom values for spec.workloadUpdateStrategy
    Note: This is needed for tests that modify such fields to default values
    """
    with update_custom_resource(
        patch={
            hyperconverged_resource_scope_function: CUSTOM_WORKLOAD_STRATEGY_SPEC.copy()
        },
    ):
        yield
    wait_for_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)
