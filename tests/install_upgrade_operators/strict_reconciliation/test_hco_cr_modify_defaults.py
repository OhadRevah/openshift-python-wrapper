import logging

import pytest
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler

import tests.install_upgrade_operators.strict_reconciliation.constants as const_src
from tests.install_upgrade_operators.strict_reconciliation.utils import (
    validate_featuregates_not_in_kv_cr,
)
from tests.install_upgrade_operators.utils import (
    get_network_addon_config,
    wait_for_spec_change,
)
from utilities.hco import get_hco_spec
from utilities.storage import get_hyperconverged_cdi
from utilities.virt import get_hyperconverged_kubevirt


LOGGER = logging.getLogger(__name__)


class TestOperatorsModify:
    @pytest.mark.parametrize(
        "updated_hco_cr, expected",
        [
            pytest.param(
                {
                    "patch": {"spec": {"certConfig": const_src.EXPCT_CERTC_DEFAULTS}},
                },
                {
                    "hco_spec": {"certConfig": const_src.EXPCT_CERTC_DEFAULTS},
                    "kubevirt_spec": const_src.KUBEVIRT_DEFAULT,
                    "cdi_spec": {"certConfig": const_src.EXPCT_CERTC_DEFAULTS},
                    "cnao_spec": {"selfSignConfiguration": const_src.CNAO_DEFAULT},
                },
                marks=pytest.mark.polarion("CNV-6698"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "certConfig": {
                                "ca": {
                                    "duration": const_src.CERTC_DEFAULT_48H,
                                },
                            }
                        }
                    },
                },
                {
                    "hco_spec": {"certConfig": const_src.HCO_MOD_DEFAUTL_CA_DUR},
                    "kubevirt_spec": const_src.KV_MOD_DEFAUTL_CA_DUR,
                    "cdi_spec": {"certConfig": const_src.HCO_MOD_DEFAUTL_CA_DUR},
                    "cnao_spec": const_src.CNAO_MOD_DEFAULT_CA_DUR,
                },
                marks=pytest.mark.polarion("CNV-6699"),
                id="Test_Modify_HCO_CR_CertConfig_ca_duration",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "certConfig": {
                                "ca": {
                                    "renewBefore": const_src.CERTC_DEFAULT_24H,
                                },
                            }
                        }
                    },
                },
                {
                    "hco_spec": {"certConfig": const_src.HCO_MOD_DEFAUTL_CA_RB},
                    "kubevirt_spec": const_src.KV_MOD_DEFAUTL_SER_RB,
                    "cdi_spec": {"certConfig": const_src.HCO_MOD_DEFAUTL_CA_RB},
                    "cnao_spec": const_src.CNAO_MOD_DEFAULT_SER_RB,
                },
                marks=pytest.mark.polarion("CNV-6700"),
                id="Test_Modify_HCO_CR_CertConfig_ca_renewBefore",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "certConfig": {
                                "server": {
                                    "duration": const_src.CERTC_DEFAULT_24H,
                                },
                            }
                        }
                    },
                },
                {
                    "hco_spec": {"certConfig": const_src.HCO_MOD_DEFAUTL_SER_DUR},
                    "kubevirt_spec": const_src.KV_MOD_DEFAUTL_SER_DUR,
                    "cdi_spec": {"certConfig": const_src.HCO_MOD_DEFAUTL_SER_DUR},
                    "cnao_spec": const_src.CNAO_MOD_DEFAULT_SER_DUR,
                },
                marks=pytest.mark.polarion("CNV-6701"),
                id="Test_Modify_HCO_CR_CertConfig_server_duration",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "certConfig": {
                                "server": {
                                    "renewBefore": const_src.CERTC_DEFAULT_12H,
                                },
                            }
                        }
                    },
                },
                {
                    "hco_spec": {"certConfig": const_src.HCO_MOD_DEFAUTL_SER_RB},
                    "kubevirt_spec": const_src.KV_MOD_DEFAUTL_SER_RB,
                    "cdi_spec": {"certConfig": const_src.HCO_MOD_DEFAUTL_SER_RB},
                    "cnao_spec": const_src.CNAO_MOD_DEFAULT_SER_RB,
                },
                marks=pytest.mark.polarion("CNV-6702"),
                id="Test_Modify_HCO_CR_CertConfig_server_renewBefore",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {"liveMigrationConfig": const_src.EXPCT_LM_DEFAULTS}
                    }
                },
                {
                    "hco_spec": {"liveMigrationConfig": const_src.EXPCT_LM_DEFAULTS},
                    "kubevirt_spec": {"migrations": const_src.EXPCT_LM_DEFAULTS},
                    "cdi_spec": None,
                    "cnao_spec": None,
                },
                marks=pytest.mark.polarion("CNV-6703"),
                id="Test_Modify_HCO_CR_liveMigrationConfig",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "liveMigrationConfig": {
                                "bandwidthPerMigration": const_src.LM_BANDWIDTHPERMIGRATION_DEFAULT,
                            }
                        }
                    }
                },
                {
                    "hco_spec": {"liveMigrationConfig": const_src.LM_CUST_DEFAULT_B},
                    "kubevirt_spec": {"migrations": const_src.LM_CUST_DEFAULT_B},
                    "cdi_spec": None,
                    "cnao_spec": None,
                },
                marks=pytest.mark.polarion("CNV-6704"),
                id="Test_Modify_HCO_CR_liveMigrationConfig_bandwidthPerMigration",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "liveMigrationConfig": {
                                "completionTimeoutPerGiB": const_src.LM_COMPLETIONTIMEOUTPERGIB_DEFAULT,
                            }
                        }
                    }
                },
                {
                    "hco_spec": {"liveMigrationConfig": const_src.LM_CUST_DEFAULT_C},
                    "kubevirt_spec": {"migrations": const_src.LM_CUST_DEFAULT_C},
                    "cdi_spec": None,
                    "cnao_spec": None,
                },
                marks=pytest.mark.polarion("CNV-6705"),
                id="Test_Modify_HCO_CR_liveMigrationConfig_completionTimeoutPerGiB",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "liveMigrationConfig": {
                                "parallelMigrationsPerCluster": const_src.LM_PARALLELMIGRATIONSPERCLUSTER_DEFAULT,
                            }
                        }
                    }
                },
                {
                    "hco_spec": {"liveMigrationConfig": const_src.LM_CUST_DEFAULT_PM},
                    "kubevirt_spec": {"migrations": const_src.LM_CUST_DEFAULT_PM},
                    "cdi_spec": None,
                    "cnao_spec": None,
                },
                marks=pytest.mark.polarion("CNV-6706"),
                id="Test_Modify_HCO_CR_liveMigrationConfig_parallelMigrationsPerCluster",
            ),
            pytest.param(
                {"patch": {"spec": {"liveMigrationConfig": const_src.LM_PO_DEFAULT}}},
                {
                    "hco_spec": {"liveMigrationConfig": const_src.LM_CUST_DEFAULT_PO},
                    "kubevirt_spec": {"migrations": const_src.LM_CUST_DEFAULT_PO},
                    "cdi_spec": None,
                    "cnao_spec": None,
                },
                marks=pytest.mark.polarion("CNV-6707"),
                id="Test_Modify_HCO_CR_liveMigrationConfig_parallelOutboundMigrationsPerNode",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "liveMigrationConfig": {
                                "progressTimeout": const_src.LM_PROGRESSTIMEOUT_DEFAULT,
                            }
                        }
                    }
                },
                {
                    "hco_spec": {"liveMigrationConfig": const_src.LM_CUST_DEFAULT_PT},
                    "kubevirt_spec": {"migrations": const_src.LM_CUST_DEFAULT_PT},
                    "cdi_spec": None,
                    "cnao_spec": None,
                },
                marks=pytest.mark.polarion("CNV-6708"),
                id="Test_Modify_HCO_CR_liveMigrationConfig_progressTimeout",
            ),
        ],
        indirect=["updated_hco_cr"],
    )
    def test_modify_hco_cr(
        self,
        hco_cr_custom_values,
        admin_client,
        hco_namespace,
        updated_hco_cr,
        expected,
    ):
        """
        Tests validates that on modifying single or multiple spec fields of HCO CR with default values,
        appropriate values are found in associated spec fields for networkaddonsconfig, cdi, kubevirt and
        hyperconverged kinds
        """
        if expected["hco_spec"]:
            wait_for_spec_change(
                expected=expected["hco_spec"],
                get_spec_func=lambda: get_hco_spec(
                    admin_client=admin_client, hco_namespace=hco_namespace
                ),
                keys=const_src.HCO_CR_FIELDS,
            )
        if expected["kubevirt_spec"]:
            wait_for_spec_change(
                expected=expected["kubevirt_spec"],
                get_spec_func=lambda: get_hyperconverged_kubevirt(
                    admin_client=admin_client, hco_namespace=hco_namespace
                )
                .instance.to_dict()
                .get("spec"),
                keys=const_src.KUBEVIRT_FIELDS,
            )
        if expected["cdi_spec"]:
            wait_for_spec_change(
                expected=expected["cdi_spec"],
                get_spec_func=lambda: get_hyperconverged_cdi(admin_client=admin_client)
                .instance.to_dict()
                .get("spec"),
                keys=const_src.CDI_FIELDS,
            )
        if expected["cnao_spec"]:
            wait_for_spec_change(
                expected=expected["cnao_spec"],
                get_spec_func=lambda: get_network_addon_config(
                    admin_client=admin_client
                )
                .instance.to_dict()
                .get("spec"),
                keys=const_src.CNAO_FIELDS,
            )

    @pytest.mark.parametrize(
        "updated_hco_cr, expected",
        [
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "featureGates": {
                                "sriovLiveMigration": const_src.FG_SRIOVLIVEMIGRATION_DEFAULT,
                                "withHostPassthroughCPU": const_src.FG_WITHHOSTPASSTHROUGHCPU_DEFAULT,
                            }
                        }
                    }
                },
                {
                    "hco_spec": {
                        "featureGates": {
                            "sriovLiveMigration": const_src.FG_SRIOVLIVEMIGRATION_DEFAULT,
                            "withHostPassthroughCPU": const_src.FG_WITHHOSTPASSTHROUGHCPU_DEFAULT,
                        },
                    },
                    "kubevirt_spec": ["WithHostPassthroughCPU", "SRIOVLiveMigration"],
                },
                marks=pytest.mark.polarion("CNV-6709"),
                id="Test_Modify_HCO_CR_featureGates",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "featureGates": {
                                "sriovLiveMigration": const_src.FG_SRIOVLIVEMIGRATION_DEFAULT,
                            }
                        }
                    }
                },
                {
                    "hco_spec": {
                        "featureGates": {
                            "sriovLiveMigration": const_src.FG_SRIOVLIVEMIGRATION_DEFAULT,
                        },
                    },
                    "kubevirt_spec": ["SRIOVLiveMigration"],
                },
                marks=pytest.mark.polarion("CNV-6710"),
                id="Test_Modify_HCO_CR_featureGates_sriovLiveMigration",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "featureGates": {
                                "withHostPassthroughCPU": const_src.FG_WITHHOSTPASSTHROUGHCPU_DEFAULT,
                            }
                        }
                    }
                },
                {
                    "hco_spec": {
                        "featureGates": {
                            "withHostPassthroughCPU": const_src.FG_WITHHOSTPASSTHROUGHCPU_DEFAULT,
                        },
                    },
                    "kubevirt_spec": ["WithHostPassthroughCPU"],
                },
                marks=pytest.mark.polarion("CNV-6711"),
                id="Test_Modify_HCO_CR_featureGates_withHostPassthroughCPU",
            ),
        ],
        indirect=["updated_hco_cr"],
    )
    def test_modify_hco_cr_fg(
        self,
        hco_cr_custom_values,
        admin_client,
        hco_namespace,
        updated_hco_cr,
        expected,
    ):
        """
        Tests validates that on modifying single or multiple spec fields of HCO CR featureGates with default values,
        appropriate values are found in associated spec fields for kubevirt and hyperconverged kinds
        """
        if expected["hco_spec"]:
            wait_for_spec_change(
                expected=expected["hco_spec"],
                get_spec_func=lambda: get_hco_spec(
                    admin_client=admin_client, hco_namespace=hco_namespace
                ),
                keys=const_src.HCO_CR_FIELDS,
            )
        if expected["kubevirt_spec"]:
            samples = TimeoutSampler(
                wait_timeout=30,
                sleep=1,
                func=validate_featuregates_not_in_kv_cr,
                admin_client=admin_client,
                hco_namespace=hco_namespace,
                feature_gates_under_test=expected["kubevirt_spec"],
            )
            try:
                for sample in samples:
                    if sample:
                        return
            except TimeoutExpiredError:
                LOGGER.error(
                    f"Timeout validating the kubevirt featureGates field."
                    f"{expected['kubevirt_spec']} was not removed from kubevirt's featureGates"
                )
                raise
