import logging

import pytest

from tests.install_upgrade_operators.strict_reconciliation import constants
from tests.install_upgrade_operators.strict_reconciliation.utils import (
    get_hco_spec,
    validate_featuregates_in_kv_cr,
    validate_featuregates_not_in_cdi_cr,
    validate_featuregates_not_in_kv_cr,
    verify_spec,
    wait_for_fg_update,
)


LOGGER = logging.getLogger(__name__)


class TestHCOOptionalFeatureGatesSuite:
    @pytest.mark.parametrize(
        ("feature_gate_under_test"),
        [
            pytest.param(
                constants.KV_SRIOV_LIVE_MIGRATION_FG_FIELD_NAME,
                marks=(pytest.mark.polarion("CNV-6267")),
                id="sriov_live_migration_not_exist_in_kubevirt_cr",
            ),
            pytest.param(
                constants.KV_WITH_HOST_PASSTHROUGH_CPU_FG_FIELD_NAME,
                marks=(pytest.mark.polarion("CNV-6268")),
                id="with_host_passthrough_cpu_not_exist_in_kubevirt_cr",
            ),
        ],
    )
    def test_optional_featuregates_not_exist_in_kubevirt_cr(
        self, kubevirt_feature_gates, feature_gate_under_test
    ):
        assert constants.KV_CR_FEATUREGATES_HCO_CR_DEFAULTS[
            feature_gate_under_test
        ] == (
            feature_gate_under_test in kubevirt_feature_gates
        ), f"{feature_gate_under_test} should not be in KubeVirt's feature gate list"

    @pytest.mark.parametrize(
        ("updated_kv_with_feature_gates", "feature_gates_under_test"),
        [
            pytest.param(
                [
                    constants.KV_SRIOV_LIVE_MIGRATION_FG_FIELD_NAME,
                    constants.KV_WITH_HOST_PASSTHROUGH_CPU_FG_FIELD_NAME,
                ],
                [
                    constants.KV_SRIOV_LIVE_MIGRATION_FG_FIELD_NAME,
                    constants.KV_WITH_HOST_PASSTHROUGH_CPU_FG_FIELD_NAME,
                ],
                marks=(pytest.mark.polarion("CNV-6269")),
                id="optional_featuregates_removed_from_kubevirt_cr",
            ),
            pytest.param(
                [constants.KV_WITH_HOST_PASSTHROUGH_CPU_FG_FIELD_NAME],
                [constants.KV_WITH_HOST_PASSTHROUGH_CPU_FG_FIELD_NAME],
                marks=(pytest.mark.polarion("CNV-6270")),
                id="optional_featuregates_withhostpassthroughcpu_removed_from_kubevirt_cr",
            ),
            pytest.param(
                [constants.KV_SRIOV_LIVE_MIGRATION_FG_FIELD_NAME],
                [constants.KV_SRIOV_LIVE_MIGRATION_FG_FIELD_NAME],
                marks=(pytest.mark.polarion("CNV-6271")),
                id="optional_featuregates_sriovlivemigration_removed_from_kubevirt_cr",
            ),
            pytest.param(
                ["fakeGate", "Sidecar"],
                ["fakeGate", "Sidecar"],
                marks=(pytest.mark.polarion("CNV-6272")),
                id="optional_featuregates_fake_removed_from_kubevirt_cr",
            ),
            pytest.param(
                ["Sidecar"],
                ["Sidecar"],
                marks=(pytest.mark.polarion("CNV-6275")),
                id="optional_featuregates_unsupported_removed_from_kubevirt_cr",
            ),
        ],
        indirect=["updated_kv_with_feature_gates"],
    )
    def test_optional_featuregates_removed_from_kubevirt_cr(
        self,
        admin_client,
        hco_namespace,
        updated_kv_with_feature_gates,
        kubevirt_feature_gates,
        feature_gates_under_test,
    ):
        wait_for_fg_update(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            expected_fg=feature_gates_under_test,
            validate_func=validate_featuregates_not_in_kv_cr,
        )

    @pytest.mark.parametrize(
        (
            "hco_with_non_default_feature_gates",
            "expected_hco_feature_gates",
            "expected_kv_feature_gates",
        ),
        [
            pytest.param(
                {
                    "fgs": ["fakeGate", "Sidecar"],
                },
                constants.EXPCT_FG_DEFAULTS,
                {
                    "fakeGate": False,
                    "Sidecar": False,
                },
                marks=(pytest.mark.polarion("CNV-6273")),
                id="optional_featuregates_fake_removed_from_hco_cr",
            ),
            pytest.param(
                {
                    "fgs": ["LiveMigration"],
                },
                constants.EXPCT_FG_DEFAULTS,
                {
                    "LiveMigration": True,
                },
                marks=(pytest.mark.polarion("CNV-6274")),
                id="optional_featuregates_hardcoded_kubevirt_feature_gates_is_removed_from_hco_cr",
            ),
            pytest.param(
                {
                    "fgs": ["Sidecar"],
                },
                constants.EXPCT_FG_DEFAULTS,
                {
                    "Sidecar": False,
                },
                marks=(pytest.mark.polarion("CNV-6276")),
                id="optional_featuregates_unsupported_removed_from_hco_cr",
            ),
            pytest.param(
                {
                    "fgs": ["HonorWaitForFirstConsumer"],
                },
                constants.EXPCT_FG_DEFAULTS,
                None,
                marks=(pytest.mark.polarion("CNV-6278")),
                id="optional_featuregates_hardcoded_cdi_feature_gates_is_removed_from_hco_cr",
            ),
            pytest.param(
                {
                    "fgs": [
                        constants.HCO_SRIOV_LIVE_MIGRATION_FG_FIELD_NAME,
                        constants.HCO_WITH_HOST_PASSTHROUGH_CPU_FG_FIELD_NAME,
                    ],
                },
                {
                    constants.HCO_WITH_HOST_PASSTHROUGH_CPU_FG_FIELD_NAME: True,
                    constants.HCO_SRIOV_LIVE_MIGRATION_FG_FIELD_NAME: True,
                },
                {
                    constants.KV_WITH_HOST_PASSTHROUGH_CPU_FG_FIELD_NAME: True,
                    constants.KV_SRIOV_LIVE_MIGRATION_FG_FIELD_NAME: True,
                },
                marks=(pytest.mark.polarion("CNV-6280")),
                id="modify_hco_cr_feature_gates",
            ),
            pytest.param(
                {
                    "fgs": [constants.HCO_WITH_HOST_PASSTHROUGH_CPU_FG_FIELD_NAME],
                },
                {
                    constants.HCO_WITH_HOST_PASSTHROUGH_CPU_FG_FIELD_NAME: True,
                    constants.HCO_SRIOV_LIVE_MIGRATION_FG_FIELD_NAME: True,
                },
                {
                    constants.KV_WITH_HOST_PASSTHROUGH_CPU_FG_FIELD_NAME: True,
                    constants.KV_SRIOV_LIVE_MIGRATION_FG_FIELD_NAME: True,
                },
                marks=(pytest.mark.polarion("CNV-6281")),
                id="modify_hco_cr_feature_gates_with_host_passthrough_cpu",
            ),
            pytest.param(
                {
                    "fgs": [constants.HCO_SRIOV_LIVE_MIGRATION_FG_FIELD_NAME],
                },
                {
                    constants.HCO_WITH_HOST_PASSTHROUGH_CPU_FG_FIELD_NAME: False,
                    constants.HCO_SRIOV_LIVE_MIGRATION_FG_FIELD_NAME: True,
                },
                {
                    constants.KV_WITH_HOST_PASSTHROUGH_CPU_FG_FIELD_NAME: False,
                    constants.KV_SRIOV_LIVE_MIGRATION_FG_FIELD_NAME: True,
                },
                marks=(pytest.mark.polarion("CNV-6282")),
                id="modify_hco_cr_feature_gates_sriov_live_migration",
            ),
        ],
        indirect=["hco_with_non_default_feature_gates"],
    )
    def test_optional_featuregates_in_hco_cr(
        self,
        admin_client,
        hco_namespace,
        hco_with_non_default_feature_gates,
        hyperconverged_resource_scope_function,
        kubevirt_feature_gates,
        expected_hco_feature_gates,
        expected_kv_feature_gates,
    ):
        verify_spec(
            expected_spec=expected_hco_feature_gates,
            get_spec_func=lambda: get_hco_spec(
                admin_client=admin_client, hco_namespace=hco_namespace
            )["featureGates"],
        )
        if expected_kv_feature_gates:
            expected_kv_fgs = [
                item
                for item in expected_kv_feature_gates
                if expected_kv_feature_gates[item]
            ]
            deleted_kv_fgs = [
                item
                for item in expected_kv_feature_gates
                if not expected_kv_feature_gates[item]
            ]
            wait_for_fg_update(
                admin_client=admin_client,
                hco_namespace=hco_namespace,
                expected_fg=expected_kv_fgs,
                validate_func=validate_featuregates_in_kv_cr,
            )

            wait_for_fg_update(
                admin_client=admin_client,
                hco_namespace=hco_namespace,
                expected_fg=deleted_kv_fgs,
                validate_func=validate_featuregates_not_in_kv_cr,
            )

    @pytest.mark.polarion("CNV-6277")
    @pytest.mark.parametrize(
        "updated_cdi_with_feature_gates",
        [["fakeGate"]],
        indirect=["updated_cdi_with_feature_gates"],
    )
    def test_optional_featuregates_fake_removed_from_cdi_cr(
        self,
        updated_cdi_with_feature_gates,
        admin_client,
        hco_namespace,
    ):
        wait_for_fg_update(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            expected_fg=["fakeGate"],
            validate_func=validate_featuregates_not_in_cdi_cr,
        )
