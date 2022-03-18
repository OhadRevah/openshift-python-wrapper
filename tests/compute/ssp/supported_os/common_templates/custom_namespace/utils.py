import logging

from ocp_resources.template import Template
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler

from utilities.constants import TIMEOUT_1MIN
from utilities.virt import get_base_templates_list


LOGGER = logging.getLogger(__name__)


def wait_for_ssp_custom_template_namespace(ssp_resource, namespace):
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_1MIN,
            sleep=2,
            func=lambda: ssp_resource.instance.spec.commonTemplates.namespace
            == namespace.name,
        ):
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"SSP Resource not updated with commonTemplates.namespace: {namespace.name}"
        )
        raise


def get_template_by_name(client, namespace_name, name):
    template = Template(client=client, name=name, namespace=namespace_name)
    assert (
        template.exists
    ), f"Template {name} was not found in namespace {namespace_name}"
    return template


def verify_base_templates_exist_in_namespace(
    client, original_base_templates, namespace
):
    expected_template_names = {template.name for template in original_base_templates}
    missing_template_names = set()
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_1MIN,
            sleep=2,
            func=get_base_templates_list,
            client=client,
        ):
            if sample:
                current_template_names = {
                    template.name
                    for template in sample
                    if template.namespace == namespace.name
                }
                missing_template_names = (
                    expected_template_names - current_template_names
                )
                if not missing_template_names:
                    return True

    except TimeoutExpiredError:
        error_message = missing_template_names or "all templates are missing"
        LOGGER.error(f"Templates not in namespace {namespace.name}: {error_message}")
        raise
