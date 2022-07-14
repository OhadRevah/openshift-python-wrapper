import logging
from copy import deepcopy

import pytest
from _pytest.outcomes import Failed
from benedict import benedict
from kubernetes.client.rest import ApiException
from ocp_resources.resource import ResourceEditor

from tests.install_upgrade_operators.hco_enablement_golden_image_updates.utils import (
    CUSTOM_CRON_TEMPLATE,
    DATA_IMPORT_CRON_ENABLE,
    KEY_PATH_SEPARATOR,
    get_template_dict_by_name,
    update_custom_template,
)
from utilities.constants import SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME
from utilities.hco import wait_for_hco_conditions


INVALID_ANNOTATION = (
    r"admission webhook.* denied the request: the dataimportcrontemplate.kubevirt.io/enable "
    r"annotation of a dataImportCronTemplate must be either.*true.*false.*"
)
LOGGER = logging.getLogger(__name__)


def get_template_dict_with_updated_annotation(template, updated_value):
    custom_template_dict = benedict(
        deepcopy(template), keypath_separator=KEY_PATH_SEPARATOR
    )
    custom_template_dict[DATA_IMPORT_CRON_ENABLE] = updated_value
    return custom_template_dict


@pytest.fixture()
def editor_hyperconverged_custom_template(
    common_templates_scope_session, hyperconverged_resource_scope_function
):
    template = deepcopy(common_templates_scope_session[0])
    del template["status"]
    custom_template_dict = get_template_dict_with_updated_annotation(
        template=template, updated_value="none"
    )
    return ResourceEditor(
        patches={
            hyperconverged_resource_scope_function: {
                "spec": {SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME: [custom_template_dict]}
            }
        },
    )


@pytest.fixture()
def updated_hco_cr_custom_template_disable(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_class,
    golden_images_namespace,
):
    custom_template_dict = get_template_dict_with_updated_annotation(
        template=CUSTOM_CRON_TEMPLATE, updated_value="false"
    )
    yield from update_custom_template(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        hyperconverged_spec=hyperconverged_resource_scope_class,
        custom_template=custom_template_dict,
        golden_images_namespace=golden_images_namespace,
    )


@pytest.mark.polarion("CNV-8731")
def test_custom_template_no_disable(
    updated_hco_cr_custom_template_disable,
    hyperconverged_status_templates_scope_function,
    ssp_spec_templates_scope_function,
):
    custom_template_name = CUSTOM_CRON_TEMPLATE["metadata"]["name"]
    for status_template in [
        hyperconverged_status_templates_scope_function,
        ssp_spec_templates_scope_function,
    ]:
        assert get_template_dict_by_name(
            template_name=custom_template_name,
            templates=status_template,
        ), f"Expected {custom_template_name} to be enabled, found: {status_template}"


@pytest.mark.polarion("CNV-8709")
def test_disable_template_annotation_value(
    admin_client, hco_namespace, editor_hyperconverged_custom_template
):
    try:
        with pytest.raises(
            ApiException,
            match=INVALID_ANNOTATION,
        ):
            editor_hyperconverged_custom_template.update(backup_resources=True)
    except Failed:
        editor_hyperconverged_custom_template.restore()
        wait_for_hco_conditions(admin_client=admin_client, hco_namespace=hco_namespace)
        raise
