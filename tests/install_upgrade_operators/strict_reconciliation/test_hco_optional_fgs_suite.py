import logging

import pytest
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler

import tests.install_upgrade_operators.strict_reconciliation.constants as src
from tests.install_upgrade_operators.strict_reconciliation.utils import (
    validate_featuregates_not_in_cdi_cr,
    validate_featuregates_not_in_kv_cr,
)


LOGGER = logging.getLogger(__name__)


KV_SRIOV_LIVE_MIGRATION_FG = "SRIOVLiveMigration"
KV_WITH_HOST_PASSTHROUGH_CPU_FG = "WithHostPassthroughCPU"
HCO_SRIOV_LIVE_MIGRATION_FG = "sriovLiveMigration"
HCO_WITH_HOST_PASSTHROUGH_CPU_FG = "withHostPassthroughCPU"


class TestHCOOptionalFeatureGatesSuite:
    @pytest.mark.parametrize(
        "feature_gate_under_test",
        [
            pytest.param(
                KV_SRIOV_LIVE_MIGRATION_FG,
                marks=(pytest.mark.polarion("CNV-6267")),
                id="sriov_live_migration_not_exist_in_kubevirt_cr",
            ),
            pytest.param(
                KV_WITH_HOST_PASSTHROUGH_CPU_FG,
                marks=(pytest.mark.polarion("CNV-6268")),
                id="with_host_passthrough_cpu_not_exist_in_kubevirt_cr",
            ),
        ],
    )
    def test_optional_featuregates_not_exist_in_kubevirt_cr(
        self, kubevirt_feature_gates, feature_gate_under_test
    ):
        assert (
            feature_gate_under_test not in kubevirt_feature_gates
        ), f"{feature_gate_under_test} should not be in KubeVirt's feature gate list"

    @pytest.mark.parametrize(
        ("updated_kv_with_feature_gates", "feature_gates_under_test"),
        [
            pytest.param(
                [KV_SRIOV_LIVE_MIGRATION_FG, KV_WITH_HOST_PASSTHROUGH_CPU_FG],
                [KV_SRIOV_LIVE_MIGRATION_FG, KV_WITH_HOST_PASSTHROUGH_CPU_FG],
                marks=(pytest.mark.polarion("CNV-6269")),
                id="optional_featuregates_removed_from_kubevirt_cr",
            ),
            pytest.param(
                [KV_WITH_HOST_PASSTHROUGH_CPU_FG],
                [KV_WITH_HOST_PASSTHROUGH_CPU_FG],
                marks=(pytest.mark.polarion("CNV-6270")),
                id="optional_featuregates_withhostpassthroughcpu_removed_from_kubevirt_cr",
            ),
            pytest.param(
                [KV_SRIOV_LIVE_MIGRATION_FG],
                [KV_SRIOV_LIVE_MIGRATION_FG],
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
        samples = TimeoutSampler(
            wait_timeout=60,
            sleep=1,
            func=validate_featuregates_not_in_kv_cr,
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            feature_gates_under_test=feature_gates_under_test,
        )
        try:
            for sample in samples:
                if sample:
                    return
        except TimeoutExpiredError:
            LOGGER.error(
                "Timeout validating the KubeVirt featureGates field."
                f" Some of the {feature_gates_under_test} are still in KubeVirt featureGates list"
            )
            raise

    @pytest.mark.parametrize(
        (
            "hco_with_non_default_feature_gates",
            "expected_hco_feature_gates",
            "expected_kv_feature_gates",
        ),
        [
            pytest.param(
                ["fakeGate", "Sidecar"],
                src.EXPCT_FG_DEFAULTS,
                {
                    "fakeGate": False,
                    "Sidecar": False,
                },
                marks=(pytest.mark.polarion("CNV-6273")),
                id="optional_featuregates_fake_removed_from_hco_cr",
            ),
            pytest.param(
                ["LiveMigration"],
                src.EXPCT_FG_DEFAULTS,
                {
                    "LiveMigration": True,
                },
                marks=(pytest.mark.polarion("CNV-6274")),
                id="optional_featuregates_hardcoded_kubevirt_feature_gates_is_removed_from_hco_cr",
            ),
            pytest.param(
                ["Sidecar"],
                src.EXPCT_FG_DEFAULTS,
                {
                    "Sidecar": False,
                },
                marks=(pytest.mark.polarion("CNV-6276")),
                id="optional_featuregates_unsupported_removed_from_hco_cr",
            ),
            pytest.param(
                ["HonorWaitForFirstConsumer"],
                src.EXPCT_FG_DEFAULTS,
                None,
                marks=(pytest.mark.polarion("CNV-6278")),
                id="optional_featuregates_hardcoded_cdi_feature_gates_is_removed_from_hco_cr",
            ),
            pytest.param(
                [HCO_SRIOV_LIVE_MIGRATION_FG, HCO_WITH_HOST_PASSTHROUGH_CPU_FG],
                {
                    HCO_WITH_HOST_PASSTHROUGH_CPU_FG: True,
                    HCO_SRIOV_LIVE_MIGRATION_FG: True,
                },
                {
                    KV_WITH_HOST_PASSTHROUGH_CPU_FG: True,
                    KV_SRIOV_LIVE_MIGRATION_FG: True,
                },
                marks=(pytest.mark.polarion("CNV-6280")),
                id="modify_hco_cr_feature_gates",
            ),
            pytest.param(
                [HCO_WITH_HOST_PASSTHROUGH_CPU_FG],
                {
                    HCO_WITH_HOST_PASSTHROUGH_CPU_FG: True,
                    HCO_SRIOV_LIVE_MIGRATION_FG: False,
                },
                {
                    KV_WITH_HOST_PASSTHROUGH_CPU_FG: True,
                    KV_SRIOV_LIVE_MIGRATION_FG: False,
                },
                marks=(pytest.mark.polarion("CNV-6281")),
                id="modify_hco_cr_feature_gates_with_host_passthrough_cpu",
            ),
            pytest.param(
                [HCO_SRIOV_LIVE_MIGRATION_FG],
                {
                    HCO_WITH_HOST_PASSTHROUGH_CPU_FG: False,
                    HCO_SRIOV_LIVE_MIGRATION_FG: True,
                },
                {
                    KV_WITH_HOST_PASSTHROUGH_CPU_FG: False,
                    KV_SRIOV_LIVE_MIGRATION_FG: True,
                },
                marks=(pytest.mark.polarion("CNV-6282")),
                id="modify_hco_cr_feature_gates_sriov_live_migration",
            ),
        ],
        indirect=["hco_with_non_default_feature_gates"],
    )
    def test_optional_featuregates_in_hco_cr(
        self,
        hco_with_non_default_feature_gates,
        hyperconverged_resource_scope_function,
        kubevirt_feature_gates,
        expected_hco_feature_gates,
        expected_kv_feature_gates,
    ):
        assert (
            hyperconverged_resource_scope_function.instance.to_dict()["spec"][
                "featureGates"
            ]
            == expected_hco_feature_gates
        ), "wrong HyperConverged's featureGates object"

        if expected_kv_feature_gates is not None:
            errors = []
            for fg, expected_in_kv in expected_kv_feature_gates.items():
                if expected_in_kv:
                    if fg not in kubevirt_feature_gates:
                        errors.append(
                            f"{fg} should be KubeVirt feature gate list, but it's not"
                        )
                else:
                    if fg in kubevirt_feature_gates:
                        errors.append(
                            f"{fg} should not be KubeVirt feature gate list, but it is"
                        )
            assert not errors, "\n".join(errors)

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
        samples = TimeoutSampler(
            wait_timeout=60,
            sleep=1,
            func=validate_featuregates_not_in_cdi_cr,
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            feature_gate_under_test="fakeGate",
        )
        try:
            for sample in samples:
                if sample:
                    return
        except TimeoutExpiredError:
            LOGGER.error(
                "Timeout validating the CDI featureGates field."
                "fakeGate was not removed from CDI's featureGates"
            )
            raise
