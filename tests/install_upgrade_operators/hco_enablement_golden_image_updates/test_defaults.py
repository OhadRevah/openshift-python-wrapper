import pytest

from tests.install_upgrade_operators.strict_reconciliation.constants import (
    COMMON_TEMPLATES_KEY_NAME,
    DATA_IMPORT_CRON_TEMPLATES_KEY_NAME,
)


@pytest.mark.polarion("CNV-7504")
def test_data_import_schedule_default_in_hco_cr(
    data_import_schedule,
):
    # example (the first and second numbers are random):
    # dataImportSchedule: 57 45/12 * * *
    assert data_import_schedule, "No crontab value found"


@pytest.mark.polarion("CNV-7473")
def test_verify_default_data_import_cron_templates_ssp_cr(
    ssp_cr_spec,
):
    assert (
        DATA_IMPORT_CRON_TEMPLATES_KEY_NAME
        not in ssp_cr_spec[COMMON_TEMPLATES_KEY_NAME]
    ), (
        "the key exists, not as expected: "
        f"key={DATA_IMPORT_CRON_TEMPLATES_KEY_NAME} spec={ssp_cr_spec}"
    )
