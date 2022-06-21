import logging
import re

from ocp_resources.data_import_cron import DataImportCron
from openshift.dynamic.exceptions import ResourceNotFoundError

from tests.install_upgrade_operators.product_upgrade.utils import get_operator_by_name
from utilities.constants import HCO_OPERATOR, SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME
from utilities.hco import wait_for_hco_conditions
from utilities.ssp import wait_for_ssp_conditions


HCO_CR_DATA_IMPORT_SCHEDULE_KEY = "dataImportSchedule"
RE_NAMED_GROUP_MINUTES = "minutes"
RE_NAMED_GROUP_HOURS = "hours"
DATA_IMPORT_SCHEDULE_RANDOM_MINUTES_REGEX = (
    rf"(?P<{RE_NAMED_GROUP_MINUTES}>\d+)\s+"
    rf"(?P<{RE_NAMED_GROUP_HOURS}>\d+)\/12\s+\*\s+\*\s+\*\s*$"
)
COMMON_TEMPLATE = "commonTemplate"

LOGGER = logging.getLogger(__name__)


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


def wait_for_auto_boot_config_stabilization(admin_client, hco_namespace):
    wait_for_ssp_conditions(admin_client=admin_client, hco_namespace=hco_namespace)
    wait_for_hco_conditions(admin_client=admin_client, hco_namespace=hco_namespace)


def get_data_import_cron_by_name(namespace, cron_name):
    data_import_cron = DataImportCron(name=cron_name, namespace=namespace)
    if data_import_cron.exists:
        return data_import_cron
    raise ResourceNotFoundError(
        f"DataImportCron: {data_import_cron} not found in namespace: {namespace}"
    )


def get_template_dict_by_name(template_name, templates):
    for template in templates:
        if template["metadata"]["name"] == template_name:
            return template
