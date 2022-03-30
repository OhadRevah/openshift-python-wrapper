import pytest

from tests.install_upgrade_operators.strict_reconciliation import constants
from tests.install_upgrade_operators.strict_reconciliation.utils import (
    assert_expected_hardcoded_feature_gates,
)
from tests.install_upgrade_operators.utils import wait_for_stabilize
from utilities.storage import get_hyperconverged_cdi
from utilities.virt import get_hyperconverged_kubevirt


pytestmark = pytest.mark.sno


class TestHardcodedFeatureGates:
    @pytest.mark.parametrize(
        "updated_delete_resource",
        [
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            "configuration": {
                                "developerConfiguration": {"featureGates": None}
                            }
                        }
                    },
                    "related_object_name": "kubevirt-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_kubevirt,
                },
                marks=pytest.mark.polarion("CNV-6427"),
                id="delete_hardcoded_featuregates_kubevirt_cr_featuregates_none",
            ),
        ],
        indirect=["updated_delete_resource"],
    )
    def test_hardcoded_featuregates_removed_from_kubevirt_cr(
        self,
        admin_client,
        hco_namespace,
        updated_delete_resource,
        expected_kubevirt_hardcoded_feature_gates,
        kubevirt_hyperconverged_spec_scope_function,
        hco_spec,
    ):
        actual_fgs = kubevirt_hyperconverged_spec_scope_function["configuration"][
            "developerConfiguration"
        ]["featureGates"]
        assert_expected_hardcoded_feature_gates(
            actual=actual_fgs,
            expected=expected_kubevirt_hardcoded_feature_gates,
            hco_spec=hco_spec,
        )

    @pytest.mark.polarion("CNV-6277")
    @pytest.mark.parametrize(
        ("updated_cdi_cr", "expected"),
        [
            pytest.param(
                {
                    "patch": {"spec": {"config": {"featureGates": None}}},
                    "related_object_name": "cdi-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_cdi,
                },
                constants.EXPECTED_CDI_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6449")),
                id="delete_hardcoded_featuregates_cdi_cr_featuregates_none",
            ),
            pytest.param(
                {
                    "patch": {"spec": {"config": {"featureGates": []}}},
                    "related_object_name": "cdi-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_cdi,
                },
                constants.EXPECTED_CDI_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6450")),
                id="delete_hardcoded_featuregates_cdi_cr_featuregates_empty_list",
            ),
            pytest.param(
                {
                    "patch": {"spec": {"config": None}},
                    "related_object_name": "cdi-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_cdi,
                },
                constants.EXPECTED_CDI_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6451")),
                id="delete_hardcoded_featuregates_cdi_cr_config_none",
            ),
            pytest.param(
                {
                    "patch": {"spec": {"config": {}}},
                    "related_object_name": "cdi-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_cdi,
                },
                constants.EXPECTED_CDI_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6452")),
                id="delete_hardcoded_featuregates_cdi_cr_config_empty_dict",
            ),
            pytest.param(
                {
                    "patch": {"spec": {}},
                    "related_object_name": "cdi-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_cdi,
                },
                constants.EXPECTED_CDI_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6640")),
                id="delete_hardcoded_featuregates_cdi_cr_spec_empty_dict",
            ),
        ],
        indirect=["updated_cdi_cr"],
    )
    def test_hardcoded_featuregates_removed_from_cdi_cr(
        self,
        admin_client,
        hco_namespace,
        updated_cdi_cr,
        expected,
        hco_spec,
    ):
        wait_for_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)
        cdi_resource = get_hyperconverged_cdi(admin_client=admin_client)
        actual_fgs = cdi_resource.instance.to_dict()["spec"]["config"]["featureGates"]
        assert_expected_hardcoded_feature_gates(
            actual=actual_fgs, expected=expected, hco_spec=hco_spec
        )
