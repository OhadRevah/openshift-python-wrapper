import pytest
from ocp_resources.cdi import CDI
from ocp_resources.namespace import Namespace
from ocp_resources.ssp import SSP

from tests.compute.ssp.supported_os.common_templates.custom_namespace.utils import (
    delete_template_by_name,
    diskless_vm_from_template,
    get_template_by_name,
    patch_template_labels,
    wait_for_ssp_custom_template_namespace,
)
from utilities.constants import OPENSHIFT_NAMESPACE
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import create_ns
from utilities.ssp import get_ssp_resource


COMMON_TEMPLATES_NAMESPACE_KEY = "commonTemplatesNamespace"


@pytest.fixture(scope="class")
def custom_vm_template_namespace(admin_client):
    yield from create_ns(name="test-custom-vm-template-ns", admin_client=admin_client)


@pytest.fixture(scope="class")
def ssp_resource_scope_class(admin_client, hco_namespace):
    return get_ssp_resource(admin_client=admin_client, namespace=hco_namespace)


@pytest.fixture(scope="class")
def opt_in_custom_template_namespace(
    admin_client,
    hco_namespace,
    custom_vm_template_namespace,
    hyperconverged_resource_scope_class,
    ssp_resource_scope_class,
):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_class: {
                "spec": {
                    COMMON_TEMPLATES_NAMESPACE_KEY: custom_vm_template_namespace.name
                }
            }
        },
        list_resource_reconcile=[SSP, CDI],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture()
def deleted_base_templates(base_templates):
    for template in base_templates:
        template.delete()
    for template in base_templates:
        template.wait_deleted()


@pytest.fixture()
def first_base_template(base_templates):
    return base_templates[0]


@pytest.fixture()
def deleted_custom_namespace_template(
    admin_client, first_base_template, custom_vm_template_namespace
):
    return delete_template_by_name(
        admin_client=admin_client,
        namespace_name=custom_vm_template_namespace.name,
        template_name=first_base_template.name,
    )


@pytest.fixture()
def base_template_from_custom_namespace(
    admin_client, first_base_template, custom_vm_template_namespace
):
    return get_template_by_name(
        client=admin_client,
        namespace_name=custom_vm_template_namespace.name,
        name=first_base_template.name,
    )


@pytest.fixture()
def edited_custom_namespace_template(
    admin_client, hco_namespace, base_template_from_custom_namespace
):
    yield from patch_template_labels(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        template=base_template_from_custom_namespace,
    )


@pytest.fixture()
def deleted_default_namespace_template(admin_client, first_base_template):
    return delete_template_by_name(
        admin_client=admin_client,
        namespace_name=OPENSHIFT_NAMESPACE,
        template_name=first_base_template.name,
    )


@pytest.fixture()
def edited_default_namespace_template(admin_client, hco_namespace, first_base_template):
    template = get_template_by_name(
        client=admin_client,
        namespace_name=OPENSHIFT_NAMESPACE,
        name=first_base_template.name,
    )
    yield from patch_template_labels(
        admin_client=admin_client, hco_namespace=hco_namespace, template=template
    )


@pytest.fixture()
def opted_out_custom_template_namespace(
    admin_client,
    hco_namespace,
    custom_vm_template_namespace,
    hyperconverged_resource_scope_function,
    ssp_resource_scope_function,
):
    ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_function: {
                "spec": {COMMON_TEMPLATES_NAMESPACE_KEY: None}
            }
        },
        list_resource_reconcile=[SSP, CDI],
        wait_for_reconcile_post_update=True,
    ).update()
    wait_for_ssp_custom_template_namespace(
        ssp_resource=ssp_resource_scope_function,
        namespace=Namespace(name=OPENSHIFT_NAMESPACE),
    )


@pytest.fixture()
def vm_from_template_labels(
    admin_client, first_base_template, custom_vm_template_namespace
):
    with diskless_vm_from_template(
        client=admin_client,
        name="custom-template-ns-vm",
        namespace=custom_vm_template_namespace,
        base_template_labels=first_base_template.labels,
    ) as vm:
        yield vm
