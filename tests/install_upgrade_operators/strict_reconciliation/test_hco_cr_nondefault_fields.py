import logging

import pytest

from tests.install_upgrade_operators.strict_reconciliation import constants
from tests.install_upgrade_operators.strict_reconciliation.utils import (
    compare_expected_with_cr,
)
from utilities.infra import BUG_STATUS_CLOSED


LOGGER = logging.getLogger(__name__)


class TestHCONonDefaultFields:
    @pytest.mark.parametrize(
        ("deleted_stanza_on_hco_cr", "resource_to_verify", "expected"),
        [
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            constants.LOCAL_STORAGE_CLASS_NAME_KEY: constants.LOCAL_STORAGE_CLASS_NAME_VALUE,
                        }
                    },
                    "raise_on_fail": False,
                },
                constants.LOCAL_STORAGE_CLASS_NAME_KEY,
                {
                    f"{constants.LOCAL_STORAGE_CLASS_NAME_VALUE}.accessMode": "ReadWriteOnce",
                    f"{constants.LOCAL_STORAGE_CLASS_NAME_VALUE}.volumeMode": "Filesystem",
                },
                marks=(
                    pytest.mark.bugzilla(
                        1968196,
                        skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED,
                    ),
                    pytest.mark.polarion("CNV-6537"),
                ),
                id="set_non_default_field_localStorageClassName",
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            constants.RESOURCE_REQUIREMENTS_KEY_HCO_CR: constants.RESOURCE_REQUIREMENTS
                        },
                    },
                },
                constants.RESOURCE_REQUIREMENTS_KEY_HCO_CR,
                constants.RESOURCE_REQUIREMENTS["storageWorkloads"],
                marks=(pytest.mark.polarion("CNV-6541")),
                id="set_non_default_field_resourceRequirements",
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            constants.SCRATCH_SPACE_STORAGE_CLASS_KEY: constants.SCRATCH_SPACE_STORAGE_CLASS_VALUE,
                        }
                    },
                },
                constants.SCRATCH_SPACE_STORAGE_CLASS_KEY,
                constants.SCRATCH_SPACE_STORAGE_CLASS_VALUE,
                marks=(pytest.mark.polarion("CNV-6542")),
                id="set_non_default_field_scratchSpaceStorageClass",
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            constants.OBSOLETE_CPUS_KEY: constants.OBSOLETE_CPUS_VALUE_HCO_CR,
                        }
                    },
                },
                constants.OBSOLETE_CPUS_KEY,
                constants.OBSOLETE_CPUS_VALUE_KUBEVIRT_CR,
                marks=(pytest.mark.polarion("CNV-6544")),
                id="set_non_default_field_obsoleteCPUs",
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            constants.VDDK_INIT_IMAGE_KEY_HCO_CR: constants.VDDK_INIT_IMAGE_VALUE,
                        }
                    },
                },
                constants.VDDK_INIT_IMAGE_KEY_HCO_CR,
                constants.VDDK_INIT_IMAGE_VALUE,
                marks=(pytest.mark.polarion("CNV-6543")),
                id="set_non_default_field_vddkInitImage",
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            constants.STORAGE_IMPORT_KEY_HCO_CR: constants.STORAGE_IMPORT_VALUE,
                        }
                    },
                },
                constants.STORAGE_IMPORT_KEY_HCO_CR,
                constants.STORAGE_IMPORT_VALUE,
                marks=(pytest.mark.polarion("CNV-6545")),
                id="set_non_default_field_storage_import",
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            constants.NP_INFRA_KEY: constants.NP_INFRA_VALUE_HCO_CR,
                        }
                    },
                },
                constants.NP_INFRA_KEY,
                constants.NP_INFRA_VALUE_CDI_CR,
                marks=(pytest.mark.polarion("CNV-6539")),
                id="set_non_default_field_infra",
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            constants.NP_WORKLOADS_KEY_HCO_CR: constants.NP_WORKLOADS_VALUE_HCO_CR,
                        }
                    },
                },
                constants.NP_WORKLOADS_KEY_HCO_CR,
                constants.NP_WORKLOADS_VALUE_CDI_CR,
                marks=(pytest.mark.polarion("CNV-6540")),
                id="set_non_default_field_workloads",
            ),
        ],
        indirect=["deleted_stanza_on_hco_cr"],
    )
    def test_non_default_fields(
        self,
        admin_client,
        hco_namespace,
        deleted_stanza_on_hco_cr,
        kubevirt_storage_class_defaults_configmap_dict,
        kubevirt_hyperconverged_spec_scope_function,
        v2v_vmware_configmap_dict,
        cdi_resource,
        resource_to_verify,
        expected,
    ):
        if resource_to_verify == constants.LOCAL_STORAGE_CLASS_NAME_KEY:
            assert not compare_expected_with_cr(
                expected=expected,
                actual=kubevirt_storage_class_defaults_configmap_dict["data"],
            )
        elif resource_to_verify == constants.OBSOLETE_CPUS_KEY:
            assert not compare_expected_with_cr(
                expected=expected,
                actual=kubevirt_hyperconverged_spec_scope_function["configuration"],
            )
        elif resource_to_verify == constants.RESOURCE_REQUIREMENTS_KEY_HCO_CR:
            assert not compare_expected_with_cr(
                expected=expected,
                actual=cdi_resource.instance.to_dict()["spec"]["config"][
                    "podResourceRequirements"
                ],
            )
        elif resource_to_verify == constants.SCRATCH_SPACE_STORAGE_CLASS_KEY:
            assert not compare_expected_with_cr(
                expected=expected,
                actual=cdi_resource.instance.to_dict()["spec"]["config"][
                    constants.SCRATCH_SPACE_STORAGE_CLASS_KEY
                ],
            )
        elif resource_to_verify == constants.STORAGE_IMPORT_KEY_HCO_CR:
            assert not compare_expected_with_cr(
                expected=expected,
                actual=cdi_resource.instance.to_dict()["spec"]["config"],
            )
        elif resource_to_verify == constants.VDDK_INIT_IMAGE_KEY_HCO_CR:
            assert not compare_expected_with_cr(
                expected=expected,
                actual=v2v_vmware_configmap_dict["data"][
                    constants.VDDK_INIT_IMAGE_KEY_CONFIGMAP
                ],
            )
        elif resource_to_verify == constants.NP_INFRA_KEY:
            assert not compare_expected_with_cr(
                expected=expected,
                actual=cdi_resource.instance.to_dict()["spec"][constants.NP_INFRA_KEY],
            )
        elif resource_to_verify == constants.NP_WORKLOADS_KEY_HCO_CR:
            assert not compare_expected_with_cr(
                expected=expected,
                actual=cdi_resource.instance.to_dict()["spec"][
                    constants.NP_WORKLOADS_KEY_CDI_CR
                ],
            )
        else:
            pytest.fail("Bad test configuration. This should never be reached.")
