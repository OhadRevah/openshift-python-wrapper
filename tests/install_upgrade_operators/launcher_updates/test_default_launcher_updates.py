import logging

import pytest

from tests.install_upgrade_operators.launcher_updates.constants import (
    DEFAULT_BATCH_EVICTION_INTERVAL,
    DEFAULT_BATCH_EVICTION_SIZE,
    DEFAULT_WORKLOAD_UPDATE_METHODS,
)
from tests.install_upgrade_operators.utils import (
    get_hco_spec,
    get_hyperconverged_kubevirt,
    wait_for_spec_change,
)
from utilities.hco import wait_for_hco_conditions


LOGGER = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "resource_name, expected",
    [
        pytest.param(
            "hyperconverged",
            {
                "workloadUpdateStrategy": {
                    "batchEvictionInterval": DEFAULT_BATCH_EVICTION_INTERVAL,
                    "batchEvictionSize": DEFAULT_BATCH_EVICTION_SIZE,
                    "workloadUpdateMethods": DEFAULT_WORKLOAD_UPDATE_METHODS,
                },
            },
            marks=(pytest.mark.polarion("CNV-6911")),
            id="test_hyperconverged_default_workload_update_strategy",
        ),
        pytest.param(
            "kubevirt",
            {
                "workloadUpdateStrategy": {
                    "batchEvictionInterval": DEFAULT_BATCH_EVICTION_INTERVAL,
                    "batchEvictionSize": DEFAULT_BATCH_EVICTION_SIZE,
                    "workloadUpdateMethods": DEFAULT_WORKLOAD_UPDATE_METHODS,
                },
            },
            marks=(pytest.mark.polarion("CNV-6912")),
            id="test_kubevirt_default_workload_update_strategy",
        ),
    ],
)
def test_hyperconverged_default_workload_update_strategy(
    admin_client, hco_namespace, resource_name, expected
):
    """Validate by default, hyperconverged's and kubevirt's spec.workloadUpdateStrategy is set to correct values"""
    LOGGER.info(
        "Ensure HCO is is in stable condition before checking for spec.workloadUpdateStrategy"
    )
    LOGGER.info(f"Validating default values:{expected} for :{resource_name}")
    wait_for_hco_conditions(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        consecutive_checks_count=3,
    )
    if resource_name == "hyperconverged":
        wait_for_spec_change(
            expected=expected,
            get_spec_func=lambda: get_hco_spec(
                admin_client=admin_client, hco_namespace=hco_namespace
            ),
            keys=["workloadUpdateStrategy"],
        )
    elif resource_name == "kubevirt":
        wait_for_spec_change(
            expected=expected,
            get_spec_func=lambda: get_hyperconverged_kubevirt(
                admin_client=admin_client, hco_namespace=hco_namespace
            )
            .instance.to_dict()
            .get("spec"),
            keys=["workloadUpdateStrategy"],
        )
    else:
        raise AssertionError(f"Unexpected resource name: {resource_name}")