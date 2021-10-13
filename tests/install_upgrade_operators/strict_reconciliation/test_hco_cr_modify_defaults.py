import logging

import pytest
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler

from tests.install_upgrade_operators.constants import (
    HCO_CR_CERT_CONFIG_CA_KEY,
    HCO_CR_CERT_CONFIG_DURATION_KEY,
    HCO_CR_CERT_CONFIG_KEY,
    HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY,
    HCO_CR_CERT_CONFIG_SERVER_KEY,
)
from tests.install_upgrade_operators.strict_reconciliation.constants import (
    CDI_CR_CERT_CONFIG_KEY,
    CERTC_DEFAULT_12H,
    CERTC_DEFAULT_24H,
    CERTC_DEFAULT_48H,
    CNAO_CERT_CONFIG_DEFAULT,
    CNAO_CR_CERT_CONFIG_KEY,
    CNAO_MOD_DEFAULT_CA_DUR,
    CNAO_MOD_DEFAULT_SER_DUR,
    CNAO_MOD_DEFAULT_SER_RB,
    COMPLETION_TIMEOUT_PER_GIB_KEY,
    EXPCT_CERTC_DEFAULTS,
    EXPCT_LM_DEFAULTS,
    FG_SRIOVLIVEMIGRATION_DEFAULT,
    FG_WITHHOSTPASSTHROUGHCPU_DEFAULT,
    HCO_CR_FIELDS,
    HCO_MOD_DEFAUTL_CA_DUR,
    HCO_MOD_DEFAUTL_CA_RB,
    HCO_MOD_DEFAUTL_SER_DUR,
    HCO_MOD_DEFAUTL_SER_RB,
    KUBEVIRT_DEFAULT,
    KUBEVIRT_FIELDS,
    KV_MOD_DEFAUTL_CA_DUR,
    KV_MOD_DEFAUTL_SER_DUR,
    KV_MOD_DEFAUTL_SER_RB,
    LIVE_MIGRATION_CONFIG_KEY,
    LM_COMPLETIONTIMEOUTPERGIB_DEFAULT,
    LM_CUST_DEFAULT_C,
    LM_CUST_DEFAULT_PM,
    LM_CUST_DEFAULT_PO,
    LM_CUST_DEFAULT_PT,
    LM_PARALLELMIGRATIONSPERCLUSTER_DEFAULT,
    LM_PO_DEFAULT,
    LM_PROGRESSTIMEOUT_DEFAULT,
    PARALLEL_MIGRATIONS_PER_CLUSTER_KEY,
    PROGRESS_TIMEOUT_KEY,
)
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
                    "patch": {"spec": {HCO_CR_CERT_CONFIG_KEY: EXPCT_CERTC_DEFAULTS}},
                },
                {
                    "hco_spec": {HCO_CR_CERT_CONFIG_KEY: EXPCT_CERTC_DEFAULTS},
                    "kubevirt_spec": KUBEVIRT_DEFAULT,
                    "cdi_spec": {HCO_CR_CERT_CONFIG_KEY: EXPCT_CERTC_DEFAULTS},
                    "cnao_spec": {CNAO_CR_CERT_CONFIG_KEY: CNAO_CERT_CONFIG_DEFAULT},
                },
                marks=pytest.mark.polarion("CNV-6698"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            HCO_CR_CERT_CONFIG_KEY: {
                                HCO_CR_CERT_CONFIG_CA_KEY: {
                                    HCO_CR_CERT_CONFIG_DURATION_KEY: CERTC_DEFAULT_48H,
                                },
                            }
                        }
                    },
                },
                {
                    "hco_spec": {HCO_CR_CERT_CONFIG_KEY: HCO_MOD_DEFAUTL_CA_DUR},
                    "kubevirt_spec": KV_MOD_DEFAUTL_CA_DUR,
                    "cdi_spec": {HCO_CR_CERT_CONFIG_KEY: HCO_MOD_DEFAUTL_CA_DUR},
                    "cnao_spec": CNAO_MOD_DEFAULT_CA_DUR,
                },
                marks=pytest.mark.polarion("CNV-6699"),
                id="Test_Modify_HCO_CR_CertConfig_ca_duration",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            HCO_CR_CERT_CONFIG_KEY: {
                                HCO_CR_CERT_CONFIG_CA_KEY: {
                                    HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY: CERTC_DEFAULT_24H,
                                },
                            }
                        }
                    },
                },
                {
                    "hco_spec": {HCO_CR_CERT_CONFIG_KEY: HCO_MOD_DEFAUTL_CA_RB},
                    "kubevirt_spec": KV_MOD_DEFAUTL_SER_RB,
                    "cdi_spec": {HCO_CR_CERT_CONFIG_KEY: HCO_MOD_DEFAUTL_CA_RB},
                    "cnao_spec": CNAO_MOD_DEFAULT_SER_RB,
                },
                marks=pytest.mark.polarion("CNV-6700"),
                id="Test_Modify_HCO_CR_CertConfig_ca_renewBefore",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            HCO_CR_CERT_CONFIG_KEY: {
                                HCO_CR_CERT_CONFIG_SERVER_KEY: {
                                    HCO_CR_CERT_CONFIG_DURATION_KEY: CERTC_DEFAULT_24H,
                                },
                            }
                        }
                    },
                },
                {
                    "hco_spec": {HCO_CR_CERT_CONFIG_KEY: HCO_MOD_DEFAUTL_SER_DUR},
                    "kubevirt_spec": KV_MOD_DEFAUTL_SER_DUR,
                    "cdi_spec": {HCO_CR_CERT_CONFIG_KEY: HCO_MOD_DEFAUTL_SER_DUR},
                    "cnao_spec": CNAO_MOD_DEFAULT_SER_DUR,
                },
                marks=pytest.mark.polarion("CNV-6701"),
                id="Test_Modify_HCO_CR_CertConfig_server_duration",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            HCO_CR_CERT_CONFIG_KEY: {
                                HCO_CR_CERT_CONFIG_SERVER_KEY: {
                                    HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY: CERTC_DEFAULT_12H,
                                },
                            }
                        }
                    },
                },
                {
                    "hco_spec": {HCO_CR_CERT_CONFIG_KEY: HCO_MOD_DEFAUTL_SER_RB},
                    "kubevirt_spec": KV_MOD_DEFAUTL_SER_RB,
                    "cdi_spec": {HCO_CR_CERT_CONFIG_KEY: HCO_MOD_DEFAUTL_SER_RB},
                    "cnao_spec": CNAO_MOD_DEFAULT_SER_RB,
                },
                marks=pytest.mark.polarion("CNV-6702"),
                id="Test_Modify_HCO_CR_CertConfig_server_renewBefore",
            ),
            pytest.param(
                {"patch": {"spec": {LIVE_MIGRATION_CONFIG_KEY: EXPCT_LM_DEFAULTS}}},
                {
                    "hco_spec": {LIVE_MIGRATION_CONFIG_KEY: EXPCT_LM_DEFAULTS},
                    "kubevirt_spec": {"migrations": EXPCT_LM_DEFAULTS},
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
                            LIVE_MIGRATION_CONFIG_KEY: {
                                COMPLETION_TIMEOUT_PER_GIB_KEY: LM_COMPLETIONTIMEOUTPERGIB_DEFAULT,
                            }
                        }
                    }
                },
                {
                    "hco_spec": {LIVE_MIGRATION_CONFIG_KEY: LM_CUST_DEFAULT_C},
                    "kubevirt_spec": {"migrations": LM_CUST_DEFAULT_C},
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
                            LIVE_MIGRATION_CONFIG_KEY: {
                                PARALLEL_MIGRATIONS_PER_CLUSTER_KEY: LM_PARALLELMIGRATIONSPERCLUSTER_DEFAULT,
                            }
                        }
                    }
                },
                {
                    "hco_spec": {LIVE_MIGRATION_CONFIG_KEY: LM_CUST_DEFAULT_PM},
                    "kubevirt_spec": {"migrations": LM_CUST_DEFAULT_PM},
                    "cdi_spec": None,
                    "cnao_spec": None,
                },
                marks=pytest.mark.polarion("CNV-6706"),
                id="Test_Modify_HCO_CR_liveMigrationConfig_parallelMigrationsPerCluster",
            ),
            pytest.param(
                {"patch": {"spec": {LIVE_MIGRATION_CONFIG_KEY: LM_PO_DEFAULT}}},
                {
                    "hco_spec": {LIVE_MIGRATION_CONFIG_KEY: LM_CUST_DEFAULT_PO},
                    "kubevirt_spec": {"migrations": LM_CUST_DEFAULT_PO},
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
                            LIVE_MIGRATION_CONFIG_KEY: {
                                PROGRESS_TIMEOUT_KEY: LM_PROGRESSTIMEOUT_DEFAULT,
                            }
                        }
                    }
                },
                {
                    "hco_spec": {LIVE_MIGRATION_CONFIG_KEY: LM_CUST_DEFAULT_PT},
                    "kubevirt_spec": {"migrations": LM_CUST_DEFAULT_PT},
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
                keys=HCO_CR_FIELDS,
            )
        if expected["kubevirt_spec"]:
            wait_for_spec_change(
                expected=expected["kubevirt_spec"],
                get_spec_func=lambda: get_hyperconverged_kubevirt(
                    admin_client=admin_client, hco_namespace=hco_namespace
                )
                .instance.to_dict()
                .get("spec"),
                keys=KUBEVIRT_FIELDS,
            )
        if expected["cdi_spec"]:
            wait_for_spec_change(
                expected=expected["cdi_spec"],
                get_spec_func=lambda: get_hyperconverged_cdi(admin_client=admin_client)
                .instance.to_dict()
                .get("spec"),
                keys=[CDI_CR_CERT_CONFIG_KEY],
            )
        if expected["cnao_spec"]:
            wait_for_spec_change(
                expected=expected["cnao_spec"],
                get_spec_func=lambda: get_network_addon_config(
                    admin_client=admin_client
                )
                .instance.to_dict()
                .get("spec"),
                keys=[CNAO_CR_CERT_CONFIG_KEY],
            )

    @pytest.mark.parametrize(
        "updated_hco_cr, expected",
        [
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "featureGates": {
                                "sriovLiveMigration": FG_SRIOVLIVEMIGRATION_DEFAULT,
                                "withHostPassthroughCPU": FG_WITHHOSTPASSTHROUGHCPU_DEFAULT,
                            }
                        }
                    }
                },
                {
                    "hco_spec": {
                        "featureGates": {
                            "sriovLiveMigration": FG_SRIOVLIVEMIGRATION_DEFAULT,
                            "withHostPassthroughCPU": FG_WITHHOSTPASSTHROUGHCPU_DEFAULT,
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
                                "sriovLiveMigration": FG_SRIOVLIVEMIGRATION_DEFAULT,
                            }
                        }
                    }
                },
                {
                    "hco_spec": {
                        "featureGates": {
                            "sriovLiveMigration": FG_SRIOVLIVEMIGRATION_DEFAULT,
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
                                "withHostPassthroughCPU": FG_WITHHOSTPASSTHROUGHCPU_DEFAULT,
                            }
                        }
                    }
                },
                {
                    "hco_spec": {
                        "featureGates": {
                            "withHostPassthroughCPU": FG_WITHHOSTPASSTHROUGHCPU_DEFAULT,
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
                keys=HCO_CR_FIELDS,
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
