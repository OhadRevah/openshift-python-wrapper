import pytest

from utilities.constants import (
    COMMON_TEMPLATES_KEY_NAME,
    SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME,
)


@pytest.mark.polarion("CNV-7473")
def test_disable_featuregate_verify_hco_cr_and_ssp_cr(
    disabled_common_boot_image_import_feature_gate_scope_function,
    ssp_cr_spec,
):
    assert (
        SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME
        not in ssp_cr_spec[COMMON_TEMPLATES_KEY_NAME]
    ), (
        "the key exists, not as expected: "
        f"key={SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME} spec={ssp_cr_spec}"
    )
