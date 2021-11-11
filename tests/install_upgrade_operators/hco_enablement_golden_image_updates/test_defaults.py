import pytest


@pytest.mark.polarion("CNV-7504")
def test_data_import_schedule_default_in_hco_cr(
    data_import_schedule,
):
    # example (the first and second numbers are random):
    # dataImportSchedule: 57 45/12 * * *
    assert data_import_schedule, "No crontab value found"
