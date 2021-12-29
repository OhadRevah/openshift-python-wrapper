import logging

import pytest

from tests.install_upgrade_operators.strict_reconciliation.constants import (
    HCO_CR_FEATURE_GATES_KEY,
)
from utilities.constants import (
    COMMON_TEMPLATES_KEY_NAME,
    ENABLE_COMMON_BOOT_IMAGE_IMPORT_FEATURE_GATE,
    SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME,
)


LOGGER = logging.getLogger(__name__)


class TestEnableCommonBootImageImport:
    @pytest.mark.polarion("CNV-7626")
    def test_set_featuregate_enable_common_boot_image_import_true_ssp_cr(
        self,
        admin_client,
        hco_namespace,
        ssp_cr_spec,
    ):
        assert ssp_cr_spec[COMMON_TEMPLATES_KEY_NAME][
            SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME
        ], f"SSP CR commonTemplates is empty: ssp_cr_spec={ssp_cr_spec}"


@pytest.mark.parametrize(
    "updated_hco_cr",
    [
        pytest.param(
            {
                "patch": {
                    "spec": {
                        HCO_CR_FEATURE_GATES_KEY: {
                            ENABLE_COMMON_BOOT_IMAGE_IMPORT_FEATURE_GATE: False
                        }
                    }
                },
            },
            marks=pytest.mark.polarion("CNV-7778"),
            id="test_enable_and_delete_featuregate_enable_common_boot_image_import_hco_cr",
        )
    ],
    indirect=True,
)
def test_enable_and_delete_featuregate_enable_common_boot_image_import_hco_cr(
    updated_hco_cr,
    hco_spec,
):
    boot_image_feature_gate = hco_spec["featureGates"][
        ENABLE_COMMON_BOOT_IMAGE_IMPORT_FEATURE_GATE
    ]
    assert (
        not boot_image_feature_gate
    ), f"FeatureGate was not disabled after deletion: hco_featuregates={hco_spec[HCO_CR_FEATURE_GATES_KEY]}"
