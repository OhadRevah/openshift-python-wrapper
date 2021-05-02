import copy


# We have to explicitly track the expected default values
# here because we cannot simply trust that the cluster
# where we are going to execute the test is always going to
# come with a vanilla configuration.
# For instance the default for spec.certConfig.server.duration
# is 48h but this is definitively too long for a test environment
# so we expect that the initial configuration will differ from the
# default one.
CERTC_DEFAULT_48H = "48h0m0s"
CERTC_DEFAULT_24H = "24h0m0s"
CERTC_DEFAULT_12H = "12h0m0s"
CERTC_CUSTOM_96H = "96h0m0s"
CERTC_CUSTOM_36H = "36h0m0s"
CERTC_CUSTOM_18H = "18h0m0s"

FG_SRIOVLIVEMIGRATION_DEFAULT = False
FG_WITHHOSTPASSTHROUGHCPU_DEFAULT = False
LM_BANDWIDTHPERMIGRATION_DEFAULT = "64Mi"
LM_COMPLETIONTIMEOUTPERGIB_DEFAULT = 800
LM_PARALLELMIGRATIONSPERCLUSTER_DEFAULT = 5
LM_PARALLELOUTBOUNDMIGRATIONSPERNODE_DEFAULT = 2
LM_PROGRESSTIMEOUT_DEFAULT = 150
LM_BANDWIDTHPERMIGRATION_CUSTOM = "96Mi"
LM_COMPLETIONTIMEOUTPERGIB_CUSTOM = 1200
LM_PARALLELMIGRATIONSPERCLUSTER_CUSTOM = 8
LM_PARALLELOUTBOUNDMIGRATIONSPERNODE_CUSTOM = 3
LM_PROGRESSTIMEOUT_CUSTOM = 225
LM_PO_DEFAULT = {
    "parallelOutboundMigrationsPerNode": LM_PARALLELOUTBOUNDMIGRATIONSPERNODE_DEFAULT,
}

EXPCT_CERTC_DEFAULTS = {
    "ca": {
        "duration": CERTC_DEFAULT_48H,
        "renewBefore": CERTC_DEFAULT_24H,
    },
    "server": {
        "duration": CERTC_DEFAULT_24H,
        "renewBefore": CERTC_DEFAULT_12H,
    },
}
EXPCT_CERTC_CUSTOM_CA_DUR = copy.deepcopy(EXPCT_CERTC_DEFAULTS)
EXPCT_CERTC_CUSTOM_CA_RB = copy.deepcopy(EXPCT_CERTC_DEFAULTS)
EXPCT_CERTC_CUSTOM_SERVER_DUR = copy.deepcopy(EXPCT_CERTC_DEFAULTS)
EXPCT_CERTC_CUSTOM_SERVER_RB = copy.deepcopy(EXPCT_CERTC_DEFAULTS)
EXPCT_CERTC_CUSTOM_CA_DUR["ca"]["duration"] = CERTC_CUSTOM_96H
EXPCT_CERTC_CUSTOM_CA_RB["ca"]["renewBefore"] = CERTC_CUSTOM_36H
EXPCT_CERTC_CUSTOM_SERVER_DUR["server"]["duration"] = CERTC_CUSTOM_36H
EXPCT_CERTC_CUSTOM_SERVER_RB["server"]["renewBefore"] = CERTC_CUSTOM_18H

EXPCT_FG_DEFAULTS = {
    "withHostPassthroughCPU": FG_WITHHOSTPASSTHROUGHCPU_DEFAULT,
    "sriovLiveMigration": FG_SRIOVLIVEMIGRATION_DEFAULT,
}
EXPCT_FG_CUSTOM_W = copy.deepcopy(EXPCT_FG_DEFAULTS)
EXPCT_FG_CUSTOM_S = copy.deepcopy(EXPCT_FG_DEFAULTS)
EXPCT_FG_CUSTOM_W["withHostPassthroughCPU"] = not FG_WITHHOSTPASSTHROUGHCPU_DEFAULT
EXPCT_FG_CUSTOM_S["sriovLiveMigration"] = not FG_SRIOVLIVEMIGRATION_DEFAULT

EXPCT_LM_DEFAULTS = {
    "parallelMigrationsPerCluster": LM_PARALLELMIGRATIONSPERCLUSTER_DEFAULT,
    "parallelOutboundMigrationsPerNode": LM_PARALLELOUTBOUNDMIGRATIONSPERNODE_DEFAULT,
    "bandwidthPerMigration": LM_BANDWIDTHPERMIGRATION_DEFAULT,
    "completionTimeoutPerGiB": LM_COMPLETIONTIMEOUTPERGIB_DEFAULT,
    "progressTimeout": LM_PROGRESSTIMEOUT_DEFAULT,
}
EXPCT_LM_CUSTOM = {
    "parallelMigrationsPerCluster": LM_PARALLELMIGRATIONSPERCLUSTER_CUSTOM,
    "parallelOutboundMigrationsPerNode": LM_PARALLELOUTBOUNDMIGRATIONSPERNODE_CUSTOM,
    "bandwidthPerMigration": LM_BANDWIDTHPERMIGRATION_CUSTOM,
    "completionTimeoutPerGiB": LM_COMPLETIONTIMEOUTPERGIB_CUSTOM,
    "progressTimeout": LM_PROGRESSTIMEOUT_CUSTOM,
}
LM_CUST_DEFAULT_PM = copy.deepcopy(EXPCT_LM_CUSTOM)
LM_CUST_DEFAULT_PO = copy.deepcopy(EXPCT_LM_CUSTOM)
LM_CUST_DEFAULT_B = copy.deepcopy(EXPCT_LM_CUSTOM)
LM_CUST_DEFAULT_C = copy.deepcopy(EXPCT_LM_CUSTOM)
LM_CUST_DEFAULT_PT = copy.deepcopy(EXPCT_LM_CUSTOM)
LM_CUST_DEFAULT_PM[
    "parallelMigrationsPerCluster"
] = LM_PARALLELMIGRATIONSPERCLUSTER_DEFAULT
LM_CUST_DEFAULT_PO[
    "parallelOutboundMigrationsPerNode"
] = LM_PARALLELOUTBOUNDMIGRATIONSPERNODE_DEFAULT
LM_CUST_DEFAULT_B["bandwidthPerMigration"] = LM_BANDWIDTHPERMIGRATION_DEFAULT
LM_CUST_DEFAULT_C["completionTimeoutPerGiB"] = LM_COMPLETIONTIMEOUTPERGIB_DEFAULT
LM_CUST_DEFAULT_PT["progressTimeout"] = LM_PROGRESSTIMEOUT_DEFAULT
EXPCT_LM_CUSTOM_PM = copy.deepcopy(EXPCT_LM_DEFAULTS)
EXPCT_LM_CUSTOM_PO = copy.deepcopy(EXPCT_LM_DEFAULTS)
EXPCT_LM_CUSTOM_B = copy.deepcopy(EXPCT_LM_DEFAULTS)
EXPCT_LM_CUSTOM_C = copy.deepcopy(EXPCT_LM_DEFAULTS)
EXPCT_LM_CUSTOM_PT = copy.deepcopy(EXPCT_LM_DEFAULTS)

EXPCT_LM_CUSTOM_PM[
    "parallelMigrationsPerCluster"
] = LM_PARALLELMIGRATIONSPERCLUSTER_CUSTOM
EXPCT_LM_CUSTOM_PO[
    "parallelOutboundMigrationsPerNode"
] = LM_PARALLELOUTBOUNDMIGRATIONSPERNODE_CUSTOM
EXPCT_LM_CUSTOM_B["bandwidthPerMigration"] = LM_BANDWIDTHPERMIGRATION_CUSTOM
EXPCT_LM_CUSTOM_C["completionTimeoutPerGiB"] = LM_COMPLETIONTIMEOUTPERGIB_CUSTOM
EXPCT_LM_CUSTOM_PT["progressTimeout"] = LM_PROGRESSTIMEOUT_CUSTOM
EXPCT_CERTC_CUSTOM = {
    "ca": {
        "duration": CERTC_CUSTOM_96H,
        "renewBefore": CERTC_CUSTOM_36H,
    },
    "server": {
        "duration": CERTC_CUSTOM_36H,
        "renewBefore": CERTC_CUSTOM_18H,
    },
}

CUSTOM_HCO_CR_SPEC = {
    "spec": {
        "liveMigrationConfig": EXPCT_LM_CUSTOM,
        "certConfig": EXPCT_CERTC_CUSTOM,
        "featureGates": {
            "sriovLiveMigration": True,
            "withHostPassthroughCPU": True,
        },
    }
}
KUBEVIRT_DEFAULT = {"selfSigned": EXPCT_CERTC_DEFAULTS}
KUBEVIRT_CUSTOM = {
    "selfSigned": EXPCT_CERTC_CUSTOM,
}
KV_MOD_DEFAUTL_CA_DUR = copy.deepcopy(KUBEVIRT_CUSTOM)
KV_MOD_DEFAUTL_CA_RB = copy.deepcopy(KUBEVIRT_CUSTOM)
KV_MOD_DEFAUTL_SER_DUR = copy.deepcopy(KUBEVIRT_CUSTOM)
KV_MOD_DEFAUTL_SER_RB = copy.deepcopy(KUBEVIRT_CUSTOM)
KV_MOD_DEFAUTL_CA_DUR["selfSigned"]["ca"]["duration"] = CERTC_DEFAULT_48H
KV_MOD_DEFAUTL_CA_RB["selfSigned"]["ca"]["renewBefore"] = CERTC_DEFAULT_24H
KV_MOD_DEFAUTL_SER_DUR["selfSigned"]["server"]["duration"] = CERTC_DEFAULT_24H
KV_MOD_DEFAUTL_SER_RB["selfSigned"]["server"]["renewBefore"] = CERTC_DEFAULT_12H
CNAO_DEFAULT = {
    "caOverlapInterval": CERTC_DEFAULT_24H,
    "caRotateInterval": CERTC_DEFAULT_48H,
    "certOverlapInterval": CERTC_DEFAULT_12H,
    "certRotateInterval": CERTC_DEFAULT_24H,
}
CNAO_CUSTOM = {
    "caOverlapInterval": CERTC_CUSTOM_36H,
    "caRotateInterval": CERTC_CUSTOM_96H,
    "certOverlapInterval": CERTC_CUSTOM_18H,
    "certRotateInterval": CERTC_CUSTOM_36H,
}
CNAO_MOD_DEFAULT_CA_DUR = copy.deepcopy(CNAO_CUSTOM)
CNAO_MOD_DEFAULT_CA_RB = copy.deepcopy(CNAO_CUSTOM)
CNAO_MOD_DEFAULT_SER_DUR = copy.deepcopy(CNAO_CUSTOM)
CNAO_MOD_DEFAULT_SER_RB = copy.deepcopy(CNAO_CUSTOM)
CNAO_MOD_DEFAULT_CA_RB["caOverlapInterval"] = CERTC_DEFAULT_48H
CNAO_MOD_DEFAULT_CA_DUR["caRotateInterval"] = CERTC_DEFAULT_24H
CNAO_MOD_DEFAULT_SER_RB["certOverlapInterval"] = CERTC_DEFAULT_24H
CNAO_MOD_DEFAULT_SER_DUR["certRotateInterval"] = CERTC_DEFAULT_12H

HCO_MOD_DEFAUTL_CA_DUR = copy.deepcopy(EXPCT_CERTC_CUSTOM)
HCO_MOD_DEFAUTL_CA_RB = copy.deepcopy(EXPCT_CERTC_CUSTOM)
HCO_MOD_DEFAUTL_SER_DUR = copy.deepcopy(EXPCT_CERTC_CUSTOM)
HCO_MOD_DEFAUTL_SER_RB = copy.deepcopy(EXPCT_CERTC_CUSTOM)
HCO_MOD_DEFAUTL_CA_DUR["ca"]["duration"] = CERTC_DEFAULT_48H
HCO_MOD_DEFAUTL_CA_RB["ca"]["renewBefore"] = CERTC_DEFAULT_24H
HCO_MOD_DEFAUTL_SER_DUR["server"]["duration"] = CERTC_DEFAULT_24H
HCO_MOD_DEFAUTL_SER_RB["server"]["renewBefore"] = CERTC_DEFAULT_12H

HCO_CR_FIELDS = ["certConfig", "liveMigrationConfig", "featureGates"]
KUBEVIRT_FIELDS = ["certificateRotateStrategy", "migrations", "configuration"]
CDI_FIELDS = ["certConfig"]
CNAO_FIELDS = ["selfSignConfiguration"]

# hardcoded featuregates
EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES = [
    "DataVolumes",
    "SRIOV",
    "LiveMigration",
    "CPUManager",
    "CPUNodeDiscovery",
    "Snapshot",
    "HotplugVolumes",
    "GPU",
    "HostDevices",
    "WithHostModelCPU",
    "HypervStrictCheck",
]
EXPECTED_CDI_HARDCODED_FEATUREGATES = [
    "HonorWaitForFirstConsumer",
]
