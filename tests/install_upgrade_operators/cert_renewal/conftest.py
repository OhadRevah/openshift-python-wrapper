import logging

import pytest

from tests.install_upgrade_operators.cert_renewal.utils import (
    get_certificates_validity_period_and_checkend_result,
)
from tests.install_upgrade_operators.constants import (
    HCO_CR_CERT_CONFIG_CA_KEY,
    HCO_CR_CERT_CONFIG_KEY,
    HCO_CR_CERT_CONFIG_SERVER_KEY,
)
from utilities.constants import TIMEOUT_1MIN, TIMEOUT_11MIN
from utilities.hco import wait_for_hco_conditions
from utilities.infra import update_custom_resource


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def hyperconverged_resource_certconfig_change(
    request, admin_client, hco_namespace, hyperconverged_resource_scope_class
):
    """
    Update HCO CR with certconfig
    """
    target_certconfig_stanza = {
        HCO_CR_CERT_CONFIG_CA_KEY: {**request.param},
        HCO_CR_CERT_CONFIG_SERVER_KEY: {**request.param},
    }
    LOGGER.info("Modifying certconfig in HCO CR")
    with update_custom_resource(
        patch={
            hyperconverged_resource_scope_class: {
                "spec": {HCO_CR_CERT_CONFIG_KEY: target_certconfig_stanza}
            }
        },
    ):
        LOGGER.info(
            "Waiting for all HCO conditions to detect that it's back to a stable configuration"
        )
        wait_for_hco_conditions(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            wait_timeout=TIMEOUT_1MIN,
            consecutive_checks_count=6,
        )
        yield


@pytest.fixture()
def initial_certificates_dates(admin_client, hco_namespace, tmpdir):
    LOGGER.info("Retrieve the certificates dates")
    return get_certificates_validity_period_and_checkend_result(
        hco_namespace_name=hco_namespace.name,
        tmpdir=tmpdir,
        seconds=TIMEOUT_11MIN,
    )
