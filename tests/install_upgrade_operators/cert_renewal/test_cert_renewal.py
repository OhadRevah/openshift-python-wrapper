import logging

import pytest

from tests.install_upgrade_operators.cert_renewal.utils import (
    verify_certificates_dates_identical_to_initial_dates,
    wait_for_certificates_renewal,
)
from tests.install_upgrade_operators.constants import (
    HCO_CR_CERT_CONFIG_DURATION_KEY,
    HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY,
)
from utilities.infra import BUG_STATUS_CLOSED


LOGGER = logging.getLogger(__name__)


class TestCertRotation:
    @pytest.mark.bugzilla(
        2001048, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    @pytest.mark.polarion("CNV-6203")
    @pytest.mark.parametrize(
        "hyperconverged_resource_certconfig_change",
        [
            pytest.param(
                {
                    HCO_CR_CERT_CONFIG_DURATION_KEY: "11m",
                    HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY: "10m",
                }
            ),
        ],
        indirect=True,
    )
    def test_certificate_renewed_in_hco(
        self,
        hco_namespace,
        hyperconverged_resource_certconfig_change,
        tmpdir,
        initial_certificates_dates,
    ):
        """
        The test verifies the proper certificate rotation/renewal in high-level, that is using the openssl command with
        the -checkend command argument.
        There are 3 steps:
        1. Get the initial certificates dates.
        2. Verify that the certificates will expire beyond the configured certConfig duration time.
        3. Verify that the certificates do not expire before they are supposed to, not renewed before they are supposed
        to.
        4. Then, it waits until the certificates are renewed, verifying that the new certificates dates are different
        from the initial ones.
        """
        LOGGER.info(
            "Verify that the certificate will expire beyond the configured duration time"
        )
        certificates_not_expired = [
            certificate
            for certificate, certificate_data in initial_certificates_dates.items()
            if certificate_data["checkend_result"] != "Certificate will expire"
        ]
        assert (
            not certificates_not_expired
        ), f"Some certificates will not expire: certificates={certificates_not_expired}"

        certificate_utils_args_dict = {
            "hco_namespace": hco_namespace,
            "initial_certificates_dates": initial_certificates_dates,
            "tmpdir": tmpdir,
        }
        verify_certificates_dates_identical_to_initial_dates(
            **certificate_utils_args_dict
        )
        wait_for_certificates_renewal(**certificate_utils_args_dict)
