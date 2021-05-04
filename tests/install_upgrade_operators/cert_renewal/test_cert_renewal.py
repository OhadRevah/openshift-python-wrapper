import logging
import time

import pytest

from tests.install_upgrade_operators.cert_renewal.utils import (
    is_certificates_validity_within_given_time,
)
from utilities.constants import TIMEOUT_11MIN


LOGGER = logging.getLogger(__name__)


class TestCertRotation:
    @pytest.mark.polarion("CNV-6203")
    @pytest.mark.parametrize(
        "hyperconverged_resource_certconfig_change",
        [
            pytest.param({"duration": "11m", "renewBefore": "10m"}),
        ],
        indirect=True,
    )
    def test_certificate_renewed_in_hco(
        self,
        hco_namespace,
        hyperconverged_resource_certconfig_change,
    ):
        """
        The test verifies the proper certificate rotation/renewal in high-level, that is using the openssl command with
        the -checkend command argument.
        There are 3 steps:
        1. The test first verifies that the certificates are valid.
        2. Then, it verifies that the certificate WILL expire after after a period of time that is equal to the
        certConfig duration field value in the HCO CR.
        3. Then, the test lets a full duration time pass and retest that the certificate is valid, indicating that
        it was renewed (with a newer expiry date).
        """
        LOGGER.info("Verify that the certificate is valid (1 second ahead)")
        assert all(
            is_certificates_validity_within_given_time(
                hco_namespace_name=hco_namespace.name, seconds=1
            ).values()
        )
        LOGGER.info(
            "Verify that the certificate will expire beyond the configured duration time"
        )
        assert not any(
            is_certificates_validity_within_given_time(
                hco_namespace_name=hco_namespace.name, seconds=TIMEOUT_11MIN
            ).values()
        )
        LOGGER.info(f"Wait to let the certificates renew: wait_seconds={TIMEOUT_11MIN}")
        time.sleep(TIMEOUT_11MIN)
        # since before the sleep the certificate would have expired after the sleep time, here we verify that
        # it is still valid within 2 seconds, which assumes that the certificates were renewed
        LOGGER.info("Verify that the certificate will not expire in 2 seconds")
        assert all(
            is_certificates_validity_within_given_time(
                hco_namespace_name=hco_namespace.name, seconds=2
            ).values()
        )
