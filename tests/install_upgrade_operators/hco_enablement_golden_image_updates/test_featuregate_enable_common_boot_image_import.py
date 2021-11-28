import pytest

from tests.install_upgrade_operators.hco_enablement_golden_image_updates.constants import (
    SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME,
)
from tests.install_upgrade_operators.hco_enablement_golden_image_updates.utils import (
    FG_ENABLE_COMMON_BOOT_IMAGE_IMPORT_KEY_NAME,
)


SSP_CR_COMMON_TEMPLATES_KEY_NAME = "commonTemplates"


@pytest.mark.usefixtures("enabled_hco_featuregate_enable_common_boot_image_import")
class TestEnableCommonBootImageImport:
    @pytest.mark.polarion("CNV-7625")
    @pytest.mark.dependency(
        name="test_set_featuregate_enable_common_boot_image_import_true_hco_cr"
    )
    def test_set_featuregate_enable_common_boot_image_import_true_hco_cr(
        self,
        hco_spec,
    ):
        assert hco_spec["featureGates"][
            FG_ENABLE_COMMON_BOOT_IMAGE_IMPORT_KEY_NAME
        ], f"FeatureGate was not enabled: featuregate={FG_ENABLE_COMMON_BOOT_IMAGE_IMPORT_KEY_NAME} hco_spec={hco_spec}"

    @pytest.mark.polarion("CNV-7626")
    @pytest.mark.dependency(
        depends=["test_set_featuregate_enable_common_boot_image_import_true_hco_cr"]
    )
    @pytest.mark.order(
        after="test_set_featuregate_enable_common_boot_image_import_true_hco_cr"
    )
    def test_set_featuregate_enable_common_boot_image_import_true_ssp_cr(
        self,
        ssp_cr_spec,
        ssp_cr_common_templates_with_schedule,
    ):
        assert (
            ssp_cr_spec[SSP_CR_COMMON_TEMPLATES_KEY_NAME][
                SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME
            ]
            == ssp_cr_common_templates_with_schedule[
                SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME
            ]
        ), (
            "SSP CR commonTemplates is not as expected: "
            f"expect={ssp_cr_common_templates_with_schedule} ssp_cr_spec={ssp_cr_spec}"
        )
