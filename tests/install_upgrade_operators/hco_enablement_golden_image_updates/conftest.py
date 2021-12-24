import pytest
from ocp_resources.pod import Pod

from tests.install_upgrade_operators.hco_enablement_golden_image_updates.utils import (
    HCO_CR_DATA_IMPORT_SCHEDULE_KEY,
    delete_hco_operator_pod,
    get_random_minutes_hours_fields_from_data_import_schedule,
)
from tests.install_upgrade_operators.product_upgrade.utils import get_operator_by_name
from utilities.constants import (
    COMMON_TEMPLATES_KEY_NAME,
    HCO_OPERATOR,
    SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME,
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


@pytest.fixture()
def deleted_hco_operator_pod(
    admin_client, hco_namespace, hyperconverged_resource_scope_function
):
    delete_hco_operator_pod(admin_client=admin_client, hco_namespace=hco_namespace)
    get_operator_by_name(
        dyn_client=admin_client,
        hco_namespace=hco_namespace.name,
        operator_name=HCO_OPERATOR,
    ).wait_for_status(status=Pod.Status.RUNNING)
    return get_random_minutes_hours_fields_from_data_import_schedule(
        target_string=hyperconverged_resource_scope_function.instance.status.get(
            HCO_CR_DATA_IMPORT_SCHEDULE_KEY
        )
    )


@pytest.fixture(scope="session")
def common_templates_from_ssp_cr(ssp_cr_spec):
    return ssp_cr_spec[COMMON_TEMPLATES_KEY_NAME][SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME]
