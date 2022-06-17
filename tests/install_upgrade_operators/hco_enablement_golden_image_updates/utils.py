import re

from tests.install_upgrade_operators.product_upgrade.utils import get_operator_by_name
from utilities.constants import HCO_OPERATOR, SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME


HCO_CR_DATA_IMPORT_SCHEDULE_KEY = "dataImportSchedule"
RE_NAMED_GROUP_MINUTES = "minutes"
RE_NAMED_GROUP_HOURS = "hours"
DATA_IMPORT_SCHEDULE_RANDOM_MINUTES_REGEX = (
    rf"(?P<{RE_NAMED_GROUP_MINUTES}>\d+)\s+"
    rf"(?P<{RE_NAMED_GROUP_HOURS}>\d+)\/12\s+\*\s+\*\s+\*\s*$"
)
COMMON_TEMPLATE = "commonTemplate"


def get_random_minutes_hours_fields_from_data_import_schedule(target_string):
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
    return re_result.group(RE_NAMED_GROUP_MINUTES), re_result.group(
        RE_NAMED_GROUP_HOURS
    )


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
        operator_name=HCO_OPERATOR,
    ).delete(wait=True)


def get_modifed_common_template_names(hyperconverged):
    return [
        template["metadata"]["name"]
        for template in get_templates_by_type_from_hco_status(
            hco_status_templates=hyperconverged.instance.to_dict()["status"][
                SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME
            ],
        )
        if template["status"].get("modified")
    ]


def get_templates_by_type_from_hco_status(
    hco_status_templates, template_type=COMMON_TEMPLATE
):
    return [
        template
        for template in hco_status_templates
        if (template_type == COMMON_TEMPLATE and template["status"].get(template_type))
        or (
            template_type == "customTemplate"
            and not template["status"].get(COMMON_TEMPLATE)
        )
    ]
