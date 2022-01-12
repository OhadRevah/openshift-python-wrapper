import logging

import pytest
from ocp_resources.template import Template

from utilities.virt import get_template_by_labels


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def sap_hana_template_labels():
    return Template.generate_template_labels(
        **{
            "os": "rhel8.4",
            "workload": Template.Workload.SAPHANA,
            "flavor": Template.Flavor.TINY,
        }
    )


@pytest.fixture(scope="module")
def sap_hana_template(admin_client, sap_hana_template_labels):
    return get_template_by_labels(
        admin_client=admin_client, template_labels=sap_hana_template_labels
    )


class TestSAPHANATemplate:
    @pytest.mark.polarion("CNV-7623")
    def test_sap_hana_template_validation_rules(self, sap_hana_template):
        assert sap_hana_template.instance.objects[0].metadata.annotations[
            f"{sap_hana_template.ApiGroup.VM_KUBEVIRT_IO}/validations"
        ], "HANA template does not have validation rules."

    @pytest.mark.polarion("CNV-7759")
    def test_sap_hana_template_machine_type(
        self, sap_hana_template, machine_type_from_kubevirt_config
    ):
        sap_hana_template_machine_type = sap_hana_template.instance.objects[
            0
        ].spec.template.spec.domain.machine.type
        assert sap_hana_template_machine_type == machine_type_from_kubevirt_config, (
            f"Hana template machine type '{sap_hana_template_machine_type or None}' does not match expected type "
            f"{machine_type_from_kubevirt_config}"
        )

    @pytest.mark.polarion("CNV-7852")
    def test_sap_hana_template_no_evict_strategy(self, sap_hana_template):
        sap_hana_template_evict_strategy = sap_hana_template.instance.objects[
            0
        ].spec.template.spec.evictionStrategy
        assert not sap_hana_template_evict_strategy, (
            "HANA template should not have evictionStrategy, current value in template: "
            f"{sap_hana_template_evict_strategy}"
        )

    @pytest.mark.polarion("CNV-7758")
    def test_sap_hana_template_provider_support_annotations(self, sap_hana_template):
        template_failed_annotations = []
        template_annotations = sap_hana_template.instance.metadata.annotations
        template_api_group = sap_hana_template.ApiGroup.TEMPLATE_KUBEVIRT_IO
        if (
            template_annotations[f"{template_api_group}/provider-support-level"]
            != "Experimental"
        ):
            template_failed_annotations.append("provider-support-level")
        if (
            template_annotations[f"{template_api_group}/provider-url"]
            != "https://www.redhat.com"
        ):
            template_failed_annotations.append("provider-url")
        if (
            template_annotations[f"{template_api_group}/provider"]
            != "Red Hat - Tech Preview"
        ):
            template_failed_annotations.append("provide")
        assert not template_failed_annotations, (
            f"HANA template failed annotations: {template_failed_annotations}, "
            f"template annotations: {template_annotations}"
        )
