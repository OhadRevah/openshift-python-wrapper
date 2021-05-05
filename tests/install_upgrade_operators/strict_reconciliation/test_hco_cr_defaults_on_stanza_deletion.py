import logging

import pytest

import tests.install_upgrade_operators.strict_reconciliation.constants as src


LOGGER = logging.getLogger(__name__)


class TestCRDefaultsOnStanzaDeletion:
    @pytest.mark.parametrize(
        "deleted_stanza_on_hco_cr, expected",
        [
            pytest.param(
                {"spec": {"certConfig": {"ca": {"duration": None}}}},
                src.EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_ca_duration_none",
                marks=(pytest.mark.polarion("CNV-6377")),
            ),
            pytest.param(
                {"spec": {"certConfig": {"ca": {"renewBefore": None}}}},
                src.EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_ca_renewbefore_none",
                marks=(pytest.mark.polarion("CNV-6378")),
            ),
            pytest.param(
                {"spec": {"certConfig": {"ca": {}}}},
                src.EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_ca_empty",
                marks=(pytest.mark.polarion("CNV-6379")),
            ),
            pytest.param(
                {"spec": {"certConfig": {"ca": None}}},
                src.EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_ca_none",
                marks=(pytest.mark.polarion("CNV-6380")),
            ),
            pytest.param(
                {"spec": {"certConfig": {"server": {"duration": None}}}},
                src.EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_server_duration_none",
                marks=(pytest.mark.polarion("CNV-6381")),
            ),
            pytest.param(
                {"spec": {"certConfig": {"server": {"renewBefore": None}}}},
                src.EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_server_renewbefore_none",
                marks=(pytest.mark.polarion("CNV-6382")),
            ),
            pytest.param(
                {"spec": {"certConfig": {"server": {}}}},
                src.EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_server_empty",
                marks=(pytest.mark.polarion("CNV-6383")),
            ),
            pytest.param(
                {"spec": {"certConfig": {"server": None}}},
                src.EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_server_none",
                marks=(pytest.mark.polarion("CNV-6384")),
            ),
            pytest.param(
                {"spec": {"certConfig": {}}},
                src.EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_empty",
                marks=(pytest.mark.polarion("CNV-6385")),
            ),
            pytest.param(
                {"spec": {"certConfig": None}},
                src.EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_none",
                marks=(pytest.mark.polarion("CNV-6386")),
            ),
            pytest.param(
                {"spec": {}},
                src.EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_spec_empty",
                marks=(pytest.mark.polarion("CNV-6387")),
            ),
            pytest.param(
                {"spec": None},
                src.EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_spec_none",
                marks=(pytest.mark.polarion("CNV-6388")),
            ),
            pytest.param(
                {},
                src.EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_empty",
                marks=(pytest.mark.polarion("CNV-6389")),
            ),
            pytest.param(
                {"spec": {"certConfig": {"ca": {"duration": src.CERTC_CUSTOM_96H}}}},
                src.EXPCT_CERTC_CUSTOM_CA_DUR,
                id="defaults_cr_custom_ca_dur",
                marks=(pytest.mark.polarion("CNV-6390")),
            ),
            pytest.param(
                {"spec": {"certConfig": {"ca": {"renewBefore": src.CERTC_CUSTOM_36H}}}},
                src.EXPCT_CERTC_CUSTOM_CA_RB,
                id="defaults_cr_custom_ca_rb",
                marks=(pytest.mark.polarion("CNV-6391")),
            ),
            pytest.param(
                {
                    "spec": {
                        "certConfig": {"server": {"duration": src.CERTC_CUSTOM_36H}}
                    }
                },
                src.EXPCT_CERTC_CUSTOM_SERVER_DUR,
                id="defaults_cr_custom_server_dur",
                marks=(pytest.mark.polarion("CNV-6392")),
            ),
            pytest.param(
                {
                    "spec": {
                        "certConfig": {"server": {"renewBefore": src.CERTC_CUSTOM_18H}}
                    }
                },
                src.EXPCT_CERTC_CUSTOM_SERVER_RB,
                id="defaults_cr_custom_server_rb",
                marks=(pytest.mark.polarion("CNV-6393")),
            ),
        ],
        indirect=["deleted_stanza_on_hco_cr"],
    )
    def test_certconfig_defaults_on_stanza_delete(
        self,
        deleted_stanza_on_hco_cr,
        hyperconverged_resource_scope_function,
        expected,
    ):
        assert (
            hyperconverged_resource_scope_function.instance.to_dict()
            .get("spec")
            .get("certConfig")
            == expected
        )

    @pytest.mark.parametrize(
        "deleted_stanza_on_hco_cr, expected",
        [
            pytest.param(
                {"spec": {"featureGates": {"withHostPassthroughCPU": None}}},
                src.EXPCT_FG_DEFAULTS,
                id="defaults_fg_whp_none",
                marks=(pytest.mark.polarion("CNV-6394")),
            ),
            pytest.param(
                {"spec": {"featureGates": {"sriovLiveMigration": None}}},
                src.EXPCT_FG_DEFAULTS,
                id="defaults_fg_slm_none",
                marks=(pytest.mark.polarion("CNV-6395")),
            ),
            pytest.param(
                {"spec": {"featureGates": {}}},
                src.EXPCT_FG_DEFAULTS,
                id="defaults_fg_empty",
                marks=(pytest.mark.polarion("CNV-6396")),
            ),
            pytest.param(
                {"spec": {"featureGates": None}},
                src.EXPCT_FG_DEFAULTS,
                id="defaults_fg_none",
                marks=(pytest.mark.polarion("CNV-6397")),
            ),
            pytest.param(
                {"spec": {}},
                src.EXPCT_FG_DEFAULTS,
                id="defaults_fg_spec_empty",
                marks=(pytest.mark.polarion("CNV-6398")),
            ),
            pytest.param(
                {"spec": None},
                src.EXPCT_FG_DEFAULTS,
                id="defaults_fg_spec_none",
                marks=(pytest.mark.polarion("CNV-6399")),
            ),
            pytest.param(
                {},
                src.EXPCT_FG_DEFAULTS,
                id="defaults_fg_cr_empty",
                marks=(pytest.mark.polarion("CNV-6400")),
            ),
            pytest.param(
                {
                    "spec": {
                        "featureGates": {
                            "withHostPassthroughCPU": not src.FG_WITHHOSTPASSTHROUGHCPU_DEFAULT
                        }
                    }
                },
                src.EXPCT_FG_CUSTOM_W,
                id="defaults_fg_custom_whp",
                marks=(pytest.mark.polarion("CNV-6401")),
            ),
            pytest.param(
                {
                    "spec": {
                        "featureGates": {
                            "sriovLiveMigration": not src.FG_SRIOVLIVEMIGRATION_DEFAULT
                        }
                    }
                },
                src.EXPCT_FG_CUSTOM_S,
                id="defaults_fg_custom_slm",
                marks=(pytest.mark.polarion("CNV-6402")),
            ),
        ],
        indirect=["deleted_stanza_on_hco_cr"],
    )
    def test_featuregates_defaults_on_stanza_delete(
        self,
        deleted_stanza_on_hco_cr,
        hyperconverged_resource_scope_function,
        expected,
    ):
        assert (
            hyperconverged_resource_scope_function.instance.to_dict()
            .get("spec")
            .get("featureGates")
            == expected
        )

    @pytest.mark.parametrize(
        "deleted_stanza_on_hco_cr, expected",
        [
            pytest.param(
                {
                    "spec": {
                        "liveMigrationConfig": {"parallelMigrationsPerCluster": None}
                    }
                },
                src.EXPCT_LM_DEFAULTS,
                id="defaults_lm_pm_none",
                marks=(pytest.mark.polarion("CNV-6403")),
            ),
            pytest.param(
                {
                    "spec": {
                        "liveMigrationConfig": {
                            "parallelOutboundMigrationsPerNode": None
                        }
                    }
                },
                src.EXPCT_LM_DEFAULTS,
                id="defaults_lm_po_none",
                marks=(pytest.mark.polarion("CNV-6404")),
            ),
            pytest.param(
                {"spec": {"liveMigrationConfig": {"bandwidthPerMigration": None}}},
                src.EXPCT_LM_DEFAULTS,
                id="defaults_lm_b_none",
                marks=(pytest.mark.polarion("CNV-6405")),
            ),
            pytest.param(
                {"spec": {"liveMigrationConfig": {"bandwidthPerMigration": None}}},
                src.EXPCT_LM_DEFAULTS,
                id="defaults_lm_c_none",
                marks=(pytest.mark.polarion("CNV-6406")),
            ),
            pytest.param(
                {"spec": {"liveMigrationConfig": {"bandwidthPerMigration": None}}},
                src.EXPCT_LM_DEFAULTS,
                id="defaults_lm_pt_none",
                marks=(pytest.mark.polarion("CNV-6407")),
            ),
            pytest.param(
                {"spec": {"liveMigrationConfig": {}}},
                src.EXPCT_LM_DEFAULTS,
                id="defaults_lm_empty",
                marks=(pytest.mark.polarion("CNV-6408")),
            ),
            pytest.param(
                {"spec": {"liveMigrationConfig": None}},
                src.EXPCT_LM_DEFAULTS,
                id="defaults_lm_none",
                marks=(pytest.mark.polarion("CNV-6409")),
            ),
            pytest.param(
                {"spec": {}},
                src.EXPCT_LM_DEFAULTS,
                id="defaults_lm_spec_empty",
                marks=(pytest.mark.polarion("CNV-6410")),
            ),
            pytest.param(
                {"spec": None},
                src.EXPCT_LM_DEFAULTS,
                id="defaults_lm_spec_none",
                marks=(pytest.mark.polarion("CNV-6411")),
            ),
            pytest.param(
                {},
                src.EXPCT_LM_DEFAULTS,
                id="defaults_lm_cr_empty",
                marks=(pytest.mark.polarion("CNV-6412")),
            ),
            pytest.param(
                {
                    "spec": {
                        "liveMigrationConfig": {
                            "parallelMigrationsPerCluster": src.LM_PARALLELMIGRATIONSPERCLUSTER_CUSTOM
                        }
                    }
                },
                src.EXPCT_LM_CUSTOM_PM,
                id="defaults_lm_custom_pm",
                marks=(pytest.mark.polarion("CNV-6413")),
            ),
            pytest.param(
                {
                    "spec": {
                        "liveMigrationConfig": {
                            "parallelOutboundMigrationsPerNode": src.LM_PARALLELOUTBOUNDMIGRATIONSPERNODE_CUSTOM
                        }
                    }
                },
                src.EXPCT_LM_CUSTOM_PO,
                id="defaults_lm_custom_po",
                marks=(pytest.mark.polarion("CNV-6414")),
            ),
            pytest.param(
                {
                    "spec": {
                        "liveMigrationConfig": {
                            "bandwidthPerMigration": src.LM_BANDWIDTHPERMIGRATION_CUSTOM
                        }
                    }
                },
                src.EXPCT_LM_CUSTOM_B,
                id="defaults_lm_custom_b",
                marks=(pytest.mark.polarion("CNV-6415")),
            ),
            pytest.param(
                {
                    "spec": {
                        "liveMigrationConfig": {
                            "completionTimeoutPerGiB": src.LM_COMPLETIONTIMEOUTPERGIB_CUSTOM
                        }
                    }
                },
                src.EXPCT_LM_CUSTOM_C,
                id="defaults_lm_custom_c",
                marks=(pytest.mark.polarion("CNV-6416")),
            ),
            pytest.param(
                {
                    "spec": {
                        "liveMigrationConfig": {
                            "progressTimeout": src.LM_PROGRESSTIMEOUT_CUSTOM
                        }
                    }
                },
                src.EXPCT_LM_CUSTOM_PT,
                id="defaults_lm_custom_pt",
                marks=(pytest.mark.polarion("CNV-6417")),
            ),
        ],
        indirect=["deleted_stanza_on_hco_cr"],
    )
    def test_livemigrationconfig_defaults_on_stanza_delete(
        self,
        deleted_stanza_on_hco_cr,
        hyperconverged_resource_scope_function,
        expected,
    ):
        assert (
            hyperconverged_resource_scope_function.instance.to_dict()
            .get("spec")
            .get("liveMigrationConfig")
            == expected
        )
