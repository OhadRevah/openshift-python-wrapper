import pytest
from ocp_resources.namespace import Namespace

from tests.compute.ssp.supported_os.common_templates.custom_namespace.utils import (
    wait_for_ssp_custom_template_namespace,
)
from utilities.constants import OPENSHIFT_NAMESPACE
from utilities.hco import ResourceEditorValidateHCOReconcile, wait_for_hco_conditions
from utilities.infra import create_ns
from utilities.ssp import get_ssp_resource, wait_for_ssp_conditions


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
        }
    ):
        wait_for_ssp_custom_template_namespace(
            ssp_resource=ssp_resource_scope_class,
            namespace=custom_vm_template_namespace,
        )
        wait_for_hco_conditions(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            consecutive_checks_count=3,
        )
        yield
    wait_for_ssp_custom_template_namespace(
        ssp_resource=ssp_resource_scope_class,
        namespace=Namespace(name=OPENSHIFT_NAMESPACE),
    )


@pytest.fixture()
def deleted_base_templates(base_templates):
    for template in base_templates:
        template.delete()
    for template in base_templates:
        template.wait_deleted()


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
        }
    ).update()
    wait_for_ssp_custom_template_namespace(
        ssp_resource=ssp_resource_scope_function,
        namespace=Namespace(name=OPENSHIFT_NAMESPACE),
    )
    wait_for_hco_conditions(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        consecutive_checks_count=3,
    )
    wait_for_ssp_conditions(admin_client=admin_client, hco_namespace=hco_namespace)
