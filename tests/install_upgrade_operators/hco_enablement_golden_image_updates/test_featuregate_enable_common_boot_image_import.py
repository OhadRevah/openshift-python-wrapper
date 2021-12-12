import logging

import pytest
from benedict import benedict
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler

from tests.install_upgrade_operators.hco_enablement_golden_image_updates.constants import (
    SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME,
)
from tests.install_upgrade_operators.hco_enablement_golden_image_updates.utils import (
    FG_ENABLE_COMMON_BOOT_IMAGE_IMPORT_KEY_NAME,
)
from utilities.constants import TIMEOUT_1MIN


LOGGER = logging.getLogger(__name__)
SSP_CR_COMMON_TEMPLATES_KEY_NAME = "commonTemplates"


@pytest.mark.usefixtures("enabled_hco_featuregate_enable_common_boot_image_import")
class TestEnableCommonBootImageImport:
    @pytest.mark.polarion("CNV-7625")
    @pytest.mark.dependency(
        name="test_set_featuregate_enable_common_boot_image_import_true_hco_cr"
    )
    @pytest.mark.order(
        before="test_set_featuregate_enable_common_boot_image_import_true_ssp_cr"
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
    def test_set_featuregate_enable_common_boot_image_import_true_ssp_cr(
        self,
        admin_client,
        hco_namespace,
        ssp_cr,
        expected_ssp_cr_common_templates_with_schedule,
    ):
        def _wait_for_common_templates_population():
            samples = TimeoutSampler(
                wait_timeout=TIMEOUT_1MIN,
                sleep=1,
                func=lambda: benedict(
                    ssp_cr.instance.to_dict()["spec"], keypath_separator=None
                ).get(
                    [
                        SSP_CR_COMMON_TEMPLATES_KEY_NAME,
                        SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME,
                    ]
                ),
            )
            try:
                for sample in samples:
                    if sample:
                        return sample
            except TimeoutExpiredError:
                LOGGER.error(
                    f"Could not get SSP CR commonTemplates: ssp_cr_spec={ssp_cr.instance.spec}"
                )
                raise

        ssp_cr_data_import_cron_templates = _wait_for_common_templates_population()
        assert (
            ssp_cr_data_import_cron_templates
            == expected_ssp_cr_common_templates_with_schedule[
                SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME
            ]
        ), (
            "SSP CR commonTemplates is not as expected: "
            f"expect={expected_ssp_cr_common_templates_with_schedule} ssp_cr_spec={ssp_cr_data_import_cron_templates}"
        )
