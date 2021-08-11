import pytest

from tests.install_upgrade_operators.launcher_updates.constants import (
    CUSTOM_BATCH_EVICTION_INTERVAL,
    CUSTOM_BATCH_EVICTION_INTERVAL_INT,
    CUSTOM_BATCH_EVICTION_SIZE,
    CUSTOM_BATCH_EVICTION_SIZE_INT,
    CUSTOM_WORKLOAD_UPDATE_METHODS,
    CUSTOM_WORKLOAD_UPDATE_STRATEGY,
    MOD_DEFAULT_BATCH_EVICTION_INTERVAL,
    MOD_DEFAULT_BATCH_EVICTION_INTERVAL_INT,
    MOD_DEFAULT_BATCH_EVICTION_INTERVAL_ZERO,
    MOD_DEFAULT_BATCH_EVICTION_SIZE,
    MOD_DEFAULT_BATCH_EVICTION_SIZE_INT,
    MOD_DEFAULT_BATCH_EVICTION_SIZE_ZERO,
    MOD_DEFAULT_WORKLOAD_UPDATE_METHOD,
    MOD_DEFAULT_WORKLOAD_UPDATE_METHOD_EMPTY,
)
from tests.install_upgrade_operators.utils import (
    get_hco_spec,
    get_hyperconverged_kubevirt,
    wait_for_spec_change,
)


class TestLauncherUpdateAll:
    @pytest.mark.parametrize(
        "resource_name, expected",
        [
            pytest.param(
                "hyperconverged",
                {
                    "workloadUpdateStrategy": CUSTOM_WORKLOAD_UPDATE_STRATEGY,
                },
                marks=pytest.mark.polarion("CNV-6926"),
                id="test_hyperconverged_modify_custom_workload_update_strategy_all",
            ),
            pytest.param(
                "kubevirt",
                {
                    "workloadUpdateStrategy": CUSTOM_WORKLOAD_UPDATE_STRATEGY,
                },
                marks=pytest.mark.polarion("CNV-6927"),
                id="test_kubevirt_modify_custom_workload_update_strategy",
            ),
        ],
    )
    def test_modify_custom_workload_update_strategy_all(
        self,
        admin_client,
        hco_namespace,
        update_workload_strategy_custom_values,
        resource_name,
        expected,
    ):
        """Validate ability to update, hyperconverged's spec.workloadUpdateStrategy to custom values"""
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


class TestCustomWorkLoadStrategy:
    @pytest.mark.parametrize(
        "update_hco_cr, expected",
        [
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "workloadUpdateStrategy": {
                                "batchEvictionInterval": CUSTOM_BATCH_EVICTION_INTERVAL
                            }
                        }
                    },
                    "clean": {"spec": {"workloadUpdateStrategy": None}},
                },
                {
                    "workloadUpdateStrategy": MOD_DEFAULT_BATCH_EVICTION_INTERVAL,
                },
                marks=pytest.mark.polarion("CNV-6932"),
                id="test_hyperconverged_modify_custom_workloadUpdateStrategy_batchEvictionInterval",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "workloadUpdateStrategy": {
                                "batchEvictionSize": CUSTOM_BATCH_EVICTION_SIZE
                            }
                        }
                    },
                    "clean": {"spec": {"workloadUpdateStrategy": None}},
                },
                {
                    "workloadUpdateStrategy": MOD_DEFAULT_BATCH_EVICTION_SIZE,
                },
                marks=pytest.mark.polarion("CNV-6933"),
                id="test_hyperconverged_modify_custom_workloadUpdateStrategy_batchEvictionSize",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "workloadUpdateStrategy": {
                                "workloadUpdateMethods": CUSTOM_WORKLOAD_UPDATE_METHODS
                            }
                        }
                    },
                    "clean": {"spec": {"workloadUpdateStrategy": None}},
                },
                {
                    "workloadUpdateStrategy": MOD_DEFAULT_WORKLOAD_UPDATE_METHOD,
                },
                marks=pytest.mark.polarion("CNV-6934"),
                id="test_hyperconverged_modify_custom_workloadUpdateStrategy_workloadUpdateMethods",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "workloadUpdateStrategy": {"workloadUpdateMethods": []}
                        }
                    },
                    "clean": {"spec": {"workloadUpdateStrategy": None}},
                },
                {
                    "workloadUpdateStrategy": MOD_DEFAULT_WORKLOAD_UPDATE_METHOD_EMPTY,
                },
                marks=pytest.mark.polarion("CNV-6935"),
                id="test_hyperconverged_modify_workloadUpdateStrategy_workloadUpdateMethods_empty",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "workloadUpdateStrategy": {"batchEvictionInterval": "0s"}
                        }
                    },
                    "clean": {"spec": {"workloadUpdateStrategy": None}},
                },
                {
                    "workloadUpdateStrategy": MOD_DEFAULT_BATCH_EVICTION_INTERVAL_ZERO,
                },
                marks=pytest.mark.polarion("CNV-6936"),
                id="test_hyperconverged_modify_workloadUpdateStrategy_batchEvictionInterval_zero",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "workloadUpdateStrategy": {
                                "batchEvictionInterval": CUSTOM_BATCH_EVICTION_INTERVAL_INT
                            }
                        }
                    },
                    "clean": {"spec": {"workloadUpdateStrategy": None}},
                },
                {
                    "workloadUpdateStrategy": MOD_DEFAULT_BATCH_EVICTION_INTERVAL_INT,
                },
                marks=pytest.mark.polarion("CNV-6937"),
                id="Test_hyperconverged_modify_workloadUpdateStrategy_batchEvictionInterval_large_value",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {"workloadUpdateStrategy": {"batchEvictionSize": 0}}
                    },
                    "clean": {"spec": {"workloadUpdateStrategy": None}},
                },
                {
                    "workloadUpdateStrategy": MOD_DEFAULT_BATCH_EVICTION_SIZE_ZERO,
                },
                marks=pytest.mark.polarion("CNV-6938"),
                id="Test_hyperconverged_modify_workloadUpdateStrategy_batchEvictionSize_zero",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "workloadUpdateStrategy": {
                                "batchEvictionSize": CUSTOM_BATCH_EVICTION_SIZE_INT
                            }
                        }
                    },
                    "clean": {"spec": {"workloadUpdateStrategy": None}},
                },
                {
                    "workloadUpdateStrategy": MOD_DEFAULT_BATCH_EVICTION_SIZE_INT,
                },
                marks=pytest.mark.polarion("CNV-6939"),
                id="test_hyperconverged_modify_workloadUpdateStrategy_batchEvictionSize_large_value",
            ),
        ],
        indirect=["update_hco_cr"],
    )
    def test_hyperconverged_modify_custom_workload_update_strategy(
        self, admin_client, hco_namespace, update_hco_cr, expected
    ):
        """Validate ability to update, hyperconverged's spec.workloadUpdateStrategy to custom values"""
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
