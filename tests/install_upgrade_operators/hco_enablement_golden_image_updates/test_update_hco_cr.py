from copy import deepcopy

import pytest

from utilities.constants import (
    COMMON_TEMPLATES_KEY_NAME,
    SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME,
)


CUSTOM_CRON_TEMPLATE = {
    "metadata": {
        "annotations": {
            "cdi.kubevirt.io/storage.bind.immediate.requested": "false",
        },
        "name": "custom-test-cron",
    },
    "spec": {
        "garbageCollect": "Outdated",
        "managedDataSource": "custom",
        "schedule": "59 55/12 * * *",
        "template": {
            "metadata": {},
            "spec": {
                "source": {
                    "registry": {
                        "imageStream": "custom-test-guest",
                        "pullMethod": "node",
                    },
                },
                "storage": {
                    "resources": {
                        "requests": {
                            "storage": "7Gi",
                        }
                    }
                },
            },
        },
    },
}


@pytest.mark.parametrize(
    "updated_hco_cr",
    [
        pytest.param(
            {
                "patch": {
                    "spec": {
                        SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME: [CUSTOM_CRON_TEMPLATE]
                    }
                }
            },
            marks=pytest.mark.polarion("CNV-7884"),
            id="test_add_custom_data_import_cron_template",
        ),
    ],
    indirect=True,
)
def test_add_custom_data_import_cron_template(
    updated_hco_cr,
    hco_spec,
    ssp_cr_spec,
):
    hco_dci_templates = hco_spec[SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME]
    ssp_dci_templates = ssp_cr_spec[COMMON_TEMPLATES_KEY_NAME][
        SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME
    ]
    custom_cron_template_name = CUSTOM_CRON_TEMPLATE["metadata"]["name"]
    hco_cr_common_template_names = [
        hco_common_template["metadata"]["name"]
        for hco_common_template in hco_dci_templates
    ]
    assert CUSTOM_CRON_TEMPLATE in hco_dci_templates, (
        f"The custom entry does not exist in HCO CR: {custom_cron_template_name} "
        f"actual hco common template names: {hco_cr_common_template_names} "
    )
    expected_custom_cron_template_in_ssp_cr_spec = deepcopy(CUSTOM_CRON_TEMPLATE)
    expected_custom_cron_template_in_ssp_cr_spec["spec"]["template"]["status"] = {}
    ssp_cr_common_template_names = [
        ssp_common_template["metadata"]["name"]
        for ssp_common_template in ssp_dci_templates
    ]
    assert expected_custom_cron_template_in_ssp_cr_spec in ssp_dci_templates, (
        f"The custom entry does not exist in SSP CR: {custom_cron_template_name}"
        f"actual common template names in SSP CR: {ssp_cr_common_template_names}"
    )
