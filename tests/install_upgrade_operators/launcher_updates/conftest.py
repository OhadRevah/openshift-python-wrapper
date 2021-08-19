import pytest

from tests.install_upgrade_operators.launcher_updates.constants import (
    CUSTOM_WORKLOAD_STRATEGY_SPEC,
)
from utilities.infra import update_custom_resource


@pytest.fixture()
def updated_workload_strategy_custom_values(
    hyperconverged_resource_scope_function,
):
    """
    This fixture updates HCO CR with custom values for spec.workloadUpdateStrategy
    Note: This is needed for tests that modifies such fields to default values
    """
    with update_custom_resource(
        patch={
            hyperconverged_resource_scope_function: CUSTOM_WORKLOAD_STRATEGY_SPEC.copy()
        },
    ):
        yield
