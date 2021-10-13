import functools
import logging

import pytest

from tests.install_upgrade_operators.constants import HCO_CR_CERT_CONFIG_KEY
from tests.install_upgrade_operators.strict_reconciliation.constants import (
    CERTC_DEFAULT_12H,
    CERTC_DEFAULT_24H,
    CERTC_DEFAULT_48H,
    CNAO_CR_CERT_CONFIG_CA_DURATION_KEY,
    CNAO_CR_CERT_CONFIG_KEY_CA_RENEW_BEFORE_KEY,
    CNAO_CR_CERT_CONFIG_KEY_SERVER_RENEW_BEFORE_KEY,
    CNAO_CR_CERT_CONFIG_SERVER_DURATION_KEY,
    EXPCT_LM_DEFAULTS,
    EXPECTED_CDI_HARDCODED_FEATUREGATES,
    EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
    FG_SRIOVLIVEMIGRATION_DEFAULT,
    FG_WITHHOSTPASSTHROUGHCPU_DEFAULT,
    KUBEVIRT_CR_CERT_CONFIG_SELF_SIGNED_KEY,
    LIVE_MIGRATION_CONFIG_KEY,
)
from tests.install_upgrade_operators.strict_reconciliation.utils import (
    compare_expected_with_cr,
    expected_certconfig_stanza,
)
from utilities.infra import BUG_STATUS_CLOSED


LOGGER = logging.getLogger(__name__)


class TestOperatorsDefaults:
    @pytest.mark.parametrize(
        ("expected", "resource_kind_str", "subkeys_list"),
        [
            pytest.param(
                expected_certconfig_stanza(),
                "hco",
                [HCO_CR_CERT_CONFIG_KEY],
                marks=(
                    pytest.mark.polarion("CNV-6108"),
                    pytest.mark.bugzilla(
                        1943217,
                        skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED,
                    ),
                ),
                id="verify_defaults_certconfig_hco_cr",
            ),
            pytest.param(
                expected_certconfig_stanza(),
                "cdi",
                [HCO_CR_CERT_CONFIG_KEY],
                marks=(pytest.mark.polarion("CNV-6109"),),
                id="verify_defaults_certconfig_cdi_cr",
            ),
            pytest.param(
                expected_certconfig_stanza(),
                "kubevirt",
                [
                    "certificateRotateStrategy",
                    KUBEVIRT_CR_CERT_CONFIG_SELF_SIGNED_KEY,
                ],
                marks=(pytest.mark.polarion("CNV-6111"),),
                id="verify_defaults_certconfig_kubevirt_cr",
            ),
            pytest.param(
                {
                    "spec": {
                        "selfSignConfiguration": {
                            CNAO_CR_CERT_CONFIG_CA_DURATION_KEY: CERTC_DEFAULT_48H,
                            CNAO_CR_CERT_CONFIG_KEY_CA_RENEW_BEFORE_KEY: CERTC_DEFAULT_24H,
                            CNAO_CR_CERT_CONFIG_SERVER_DURATION_KEY: CERTC_DEFAULT_24H,
                            CNAO_CR_CERT_CONFIG_KEY_SERVER_RENEW_BEFORE_KEY: CERTC_DEFAULT_12H,
                        }
                    }
                },
                "cnao",
                [],
                marks=(pytest.mark.polarion("CNV-6112"),),
                id="verify_defaults_certconfig_cnao_cr",
            ),
            pytest.param(
                {
                    "featureGates": {
                        "sriovLiveMigration": FG_SRIOVLIVEMIGRATION_DEFAULT,
                        "withHostPassthroughCPU": FG_WITHHOSTPASSTHROUGHCPU_DEFAULT,
                    }
                },
                "hco",
                [],
                marks=(pytest.mark.polarion("CNV-6115"),),
                id="verify_defaults_optional_featuregates_hco_cr",
            ),
            pytest.param(
                {
                    LIVE_MIGRATION_CONFIG_KEY: EXPCT_LM_DEFAULTS,
                },
                "hco",
                [],
                marks=(
                    pytest.mark.polarion("CNV-6122"),
                    pytest.mark.bugzilla(
                        1862701,
                        skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED,
                    ),
                ),
                id="verify_defaults_livemigrationconfig_hco_cr",
            ),
            pytest.param(
                {
                    "configuration": {
                        "migrations": EXPCT_LM_DEFAULTS,
                    }
                },
                "kubevirt",
                [],
                marks=(
                    pytest.mark.polarion("CNV-6652"),
                    pytest.mark.bugzilla(
                        1862701,
                        skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED,
                    ),
                ),
                id="verify_defaults_livemigrationconfig_kubevirt_cr",
            ),
            pytest.param(
                EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
                "kubevirt",
                ["configuration", "developerConfiguration", "featureGates"],
                marks=(
                    pytest.mark.polarion("CNV-6426"),
                    pytest.mark.bugzilla(
                        1862701,
                        skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED,
                    ),
                ),
                id="verify_defaults_hardcoded_featuregates_kubevirt_cr",
            ),
            pytest.param(
                EXPECTED_CDI_HARDCODED_FEATUREGATES,
                "cdi",
                ["config", "featureGates"],
                marks=(pytest.mark.polarion("CNV-6448"),),
                id="verify_defaults_hardcoded_featuregates_cdi_cr",
            ),
            pytest.param(
                {
                    "obsoleteCPUModels": {
                        "486": True,
                        "Conroe": True,
                        "athlon": True,
                        "core2duo": True,
                        "coreduo": True,
                        "kvm32": True,
                        "kvm64": True,
                        "n270": True,
                        "pentium": True,
                        "pentium2": True,
                        "pentium3": True,
                        "pentiumpro": True,
                        "phenom": True,
                        "qemu32": True,
                        "qemu64": True,
                    },
                },
                "kubevirt",
                ["configuration"],
                marks=(pytest.mark.polarion("CNV-6124"),),
                id="verify_defaults_obsoleteCPUModels_kubevirt_cr",
            ),
        ],
    )
    def test_verify_expected_config_in_crs(
        self,
        expected,
        resource_kind_str,
        subkeys_list,
        cr_func_map,
    ):
        """
        Verify the default values for all stanzas that have defaults in all CRs
        """
        assert not compare_expected_with_cr(
            expected=expected,
            actual=functools.reduce(
                lambda spec, subkeys: spec[subkeys],
                subkeys_list,
                cr_func_map[resource_kind_str],
            ),
        )

    @pytest.mark.parametrize(
        "expected_to_be_absent, resource_kind_str",
        [
            pytest.param(
                "obsoletecpu",
                "hco",
                marks=(
                    pytest.mark.polarion("CNV-6124"),
                    pytest.mark.bugzilla(
                        1954486,
                        skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED,
                    ),
                ),
                id="verify_no_defaults_obsoletecpu_hco_cr",
            ),
            pytest.param(
                "permitted",
                "hco",
                marks=(
                    pytest.mark.polarion("CNV-6653"),
                    pytest.mark.bugzilla(
                        1969912,
                        skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED,
                    ),
                ),
                id="verify_no_defaults_permittedhostdevices_hco_cr",
            ),
            pytest.param(
                "permitted",
                "kubevirt",
                marks=(
                    pytest.mark.polarion("CNV-6654"),
                    pytest.mark.bugzilla(
                        1969912,
                        skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED,
                    ),
                ),
                id="verify_no_defaults_permittedhostdevices_kubevirt_cr",
            ),
        ],
    )
    def test_no_defaults_in_cr_for_permittedhostdevices_and_obsoletecpu(
        self,
        expected_to_be_absent,
        resource_kind_str,
        cr_func_map,
    ):
        assert expected_to_be_absent not in str(cr_func_map[resource_kind_str]).lower()
