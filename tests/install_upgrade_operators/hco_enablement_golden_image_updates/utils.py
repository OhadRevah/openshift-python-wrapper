import re

from tests.install_upgrade_operators.product_upgrade.utils import get_operator_by_name


HCO_CR_DATA_IMPORT_SCHEDULE_KEY = "dataImportSchedule"
DATA_IMPORT_SCHEDULE_RANDOM_MINUTES_REGEX = r"(\d+)\s+\*\/12\s+\*\s+\*\s+\*\s*$"


def get_random_minutes_field_from_data_import_schedule(target_string):
    """
    Gets the minutes field from the dataImportSchedule field in HCO CR

    Args:
        target_string (str): dataImportSchedule string (crontab format)

    Raises:
        AssertionError: raised if the regex pattern did not find a match
    """
    re_result = re.match(DATA_IMPORT_SCHEDULE_RANDOM_MINUTES_REGEX, target_string)
    assert re_result, (
        "No regex match against the string: "
        f"regex={DATA_IMPORT_SCHEDULE_RANDOM_MINUTES_REGEX} target_value={target_string}"
    )
    return re_result.group(1)


def delete_hco_operator_pod(admin_client, hco_namespace):
    """
    Deletes the HCO operator pod

    Args:
        admin_client (DynamicClient): Dynamic client object
        hco_namespace (Namespace): Namespace object
    """
    get_operator_by_name(
        dyn_client=admin_client,
        hco_namespace=hco_namespace.name,
        operator_name="hco-operator",
    ).delete(wait=True)