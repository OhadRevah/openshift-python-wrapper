import logging

import pytest

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


@pytest.mark.polarion("CNV-7778")
def test_enable_and_delete_featuregate_enable_common_boot_image_import_hco_cr(
    disabled_common_boot_image_import_feature_gate_scope_function,
    hco_spec,
):
    assert not hco_spec["featureGates"][
        ENABLE_COMMON_BOOT_IMAGE_IMPORT_FEATURE_GATE
    ], f"FeatureGate {ENABLE_COMMON_BOOT_IMAGE_IMPORT_FEATURE_GATE} was not disabled."
