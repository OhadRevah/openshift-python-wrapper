import pytest

from tests.install_upgrade_operators.hco_enablement_golden_image_updates.utils import (
    HCO_CR_DATA_IMPORT_SCHEDULE_KEY,
    get_random_minutes_hours_fields_from_data_import_schedule,
)


@pytest.fixture()
def data_import_schedule(hyperconverged_resource_scope_function):
    return hyperconverged_resource_scope_function.instance.status.get(
        HCO_CR_DATA_IMPORT_SCHEDULE_KEY
    )


@pytest.fixture()
def data_import_schedule_minute_and_hour_values(data_import_schedule):
    return get_random_minutes_hours_fields_from_data_import_schedule(
        target_string=data_import_schedule
    )
