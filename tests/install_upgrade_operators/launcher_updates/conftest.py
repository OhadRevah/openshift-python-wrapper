import pytest

from tests.install_upgrade_operators.launcher_updates.constants import (
    CUSTOM_WORKLOAD_STRATEGY_SPEC,
)
from utilities.hco import modify_hco_cr


@pytest.fixture()
def update_workload_strategy_custom_values(
    hyperconverged_resource_scope_function,
):
    """
    This fixture updates HCO CR with custom values for spec.workloadUpdateStrategy
    Note: This is needed for tests that modifies such fields to default values

    Args:
        hyperconverged_resource_scope_function (HyperConverged): HCO CR

    """
    modify_hco_cr(
        patch=CUSTOM_WORKLOAD_STRATEGY_SPEC.copy(),
        hco=hyperconverged_resource_scope_function,
    )
    yield
    modify_hco_cr(
        patch={
            "spec": {
                "workloadUpdateStrategy": None,
            }
        },
        hco=hyperconverged_resource_scope_function,
    )
