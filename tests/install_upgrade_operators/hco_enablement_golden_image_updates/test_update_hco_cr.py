from copy import deepcopy

import pytest

from tests.install_upgrade_operators.hco_enablement_golden_image_updates.utils import (
    CUSTOM_CRON_TEMPLATE,
    get_template_dict_by_name,
    get_templates_by_type_from_hco_status,
    update_custom_template,
)


def validate_template_dict(template_dict, resource_string):
    custom_template_name = CUSTOM_CRON_TEMPLATE["metadata"]["name"]
    custom_template_dict = get_template_dict_by_name(
        template_name=custom_template_name, templates=template_dict
    )
    assert custom_template_dict, (
        f"Custom template: {custom_template_name} not found "
        f"in {resource_string}: {template_dict}"
    )
    template_copy = deepcopy(custom_template_dict)
    if "status" in template_copy:
        del template_copy["status"]
    del template_copy["spec"]["template"]["status"]
    assert CUSTOM_CRON_TEMPLATE == template_copy, (
        f"Custom template: {CUSTOM_CRON_TEMPLATE} is not found "
        f"in hco.status: {template_copy}"
    )


@pytest.fixture(scope="class")
def updated_hco_cr_custom_template_scope_class(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_class,
    golden_images_namespace,
):
    yield from update_custom_template(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        hyperconverged_spec=hyperconverged_resource_scope_class,
        custom_template=CUSTOM_CRON_TEMPLATE,
        golden_images_namespace=golden_images_namespace,
    )


@pytest.mark.usefixtures("updated_hco_cr_custom_template_scope_class")
class TestCustomTemplates:
    @pytest.mark.polarion("CNV-8707")
    def test_custom_template_status(
        self, hyperconverged_status_templates_scope_function
    ):
        custom_template_name = CUSTOM_CRON_TEMPLATE["metadata"]["name"]
        custom_templates_name = [
            template["metadata"]["name"]
            for template in get_templates_by_type_from_hco_status(
                hco_status_templates=hyperconverged_status_templates_scope_function,
                template_type="customTemplate",
            )
        ]
        assert custom_template_name in custom_templates_name, (
            f"Custom template: {custom_template_name} is not found"
            f" in hco.status: {custom_templates_name}"
        )

    @pytest.mark.polarion("CNV-7884")
    def test_add_custom_data_import_cron_template(
        self,
        hyperconverged_status_templates_scope_function,
        ssp_spec_templates_scope_function,
    ):
        validate_template_dict(
            template_dict=hyperconverged_status_templates_scope_function,
            resource_string="HCO.status",
        )
        validate_template_dict(
            template_dict=ssp_spec_templates_scope_function, resource_string="SSP.spec"
        )