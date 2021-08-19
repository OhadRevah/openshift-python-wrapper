import pytest

from tests.install_upgrade_operators.launcher_updates.constants import (
    DEFAULT_WORKLOAD_UPDATE_STRATEGY,
    MOD_CUST_DEFAULT_BATCH_EVICTION_INTERVAL,
    MOD_CUST_DEFAULT_BATCH_EVICTION_SIZE,
    MOD_CUST_DEFAULT_WORKLOAD_UPDATE_METHOD,
)
from tests.install_upgrade_operators.utils import (
    get_hco_spec,
    get_hyperconverged_kubevirt,
    wait_for_spec_change,
)


class TestLauncherUpdateResetFields:
    @pytest.mark.parametrize(
        "updated_hco_cr, expected",
        [
            pytest.param(
                {
                    "patch": {"spec": {"workloadUpdateStrategy": None}},
                },
                {
                    "workloadUpdateStrategy": DEFAULT_WORKLOAD_UPDATE_STRATEGY,
                },
                marks=pytest.mark.polarion("CNV-6928"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "workloadUpdateStrategy": {"batchEvictionInterval": None}
                        }
                    },
                },
                {
                    "workloadUpdateStrategy": MOD_CUST_DEFAULT_BATCH_EVICTION_INTERVAL,
                },
                marks=pytest.mark.polarion("CNV-6929"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {"workloadUpdateStrategy": {"batchEvictionSize": None}}
                    },
                },
                {
                    "workloadUpdateStrategy": MOD_CUST_DEFAULT_BATCH_EVICTION_SIZE,
                },
                marks=pytest.mark.polarion("CNV-6930"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "workloadUpdateStrategy": {"workloadUpdateMethods": None}
                        }
                    },
                },
                {
                    "workloadUpdateStrategy": MOD_CUST_DEFAULT_WORKLOAD_UPDATE_METHOD,
                },
                marks=pytest.mark.polarion("CNV-6931"),
            ),
        ],
        indirect=["updated_hco_cr"],
    )
    def test_hyperconverged_reset_custom_workload_update_strategy(
        self,
        updated_workload_strategy_custom_values,
        admin_client,
        hco_namespace,
        updated_hco_cr,
        expected,
    ):
        """Validate ability to reset, hyperconverged's spec.workloadUpdateStrategy from custom values"""
        wait_for_spec_change(
            expected=expected,
            get_spec_func=lambda: get_hco_spec(
                admin_client=admin_client, hco_namespace=hco_namespace
            ),
            keys=["workloadUpdateStrategy"],
        )
        wait_for_spec_change(
            expected=expected,
            get_spec_func=lambda: get_hyperconverged_kubevirt(
                admin_client=admin_client, hco_namespace=hco_namespace
            )
            .instance.to_dict()
            .get("spec"),
            keys=["workloadUpdateStrategy"],
        )
