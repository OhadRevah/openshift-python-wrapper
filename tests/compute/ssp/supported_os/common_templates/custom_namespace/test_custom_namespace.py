import pytest
from ocp_resources.namespace import Namespace
from openshift.dynamic.exceptions import ForbiddenError

from tests.compute.ssp.supported_os.common_templates.custom_namespace.utils import (
    get_template_by_name,
    verify_base_templates_exist_in_namespace,
)
from utilities.constants import OPENSHIFT_NAMESPACE, UNPRIVILEGED_USER


TESTS_CLASS_NAME = "TestCustomNamespace"


@pytest.mark.usefixtures("base_templates", "opt_in_custom_template_namespace")
class TestCustomNamespace:
    @pytest.mark.polarion("CNV-8144")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::test_base_templates_exist_in_custom_namespace"
    )
    def test_base_templates_exist_in_custom_namespace(
        self,
        admin_client,
        base_templates,
        custom_vm_template_namespace,
    ):
        verify_base_templates_exist_in_namespace(
            client=admin_client,
            original_base_templates=base_templates,
            namespace=custom_vm_template_namespace,
        )

    @pytest.mark.polarion("CNV-8238")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::test_unprivileged_user_cannot_access_custom_namespace",
        depends=[f"{TESTS_CLASS_NAME}::test_base_templates_exist_in_custom_namespace"],
    )
    def test_unprivileged_user_cannot_access_custom_namespace(
        self,
        unprivileged_client,
        custom_vm_template_namespace,
    ):
        template_name = "rhel8-server-tiny"
        with pytest.raises(
            ForbiddenError,
            match=rf'.*[\\]+"{template_name}[\\]+" is forbidden: '
            rf'User [\\]+"{UNPRIVILEGED_USER}[\\]+" cannot get resource [\\]+"templates[\\]+".*',
        ):
            get_template_by_name(
                client=unprivileged_client,
                namespace_name=custom_vm_template_namespace.name,
                name=template_name,
            )

    @pytest.mark.polarion("CNV-8143")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::test_base_templates_exist_in_default_namespace_after_revert",
        depends=[
            f"{TESTS_CLASS_NAME}::test_unprivileged_user_cannot_access_custom_namespace"
        ],
    )
    def test_base_templates_exist_in_default_namespace_after_revert(
        self,
        admin_client,
        hco_namespace,
        base_templates,
        deleted_base_templates,
        opted_out_custom_template_namespace,
    ):
        verify_base_templates_exist_in_namespace(
            client=admin_client,
            original_base_templates=base_templates,
            namespace=Namespace(name=OPENSHIFT_NAMESPACE),
        )
