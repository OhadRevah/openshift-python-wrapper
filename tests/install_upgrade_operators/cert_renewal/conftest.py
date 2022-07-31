import logging

import pytest
from ocp_resources.cdi import CDI
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.secret import Secret

from tests.install_upgrade_operators.cert_renewal.constants import (
    VIRT_TEMPLATE_VALIDATOR_CERTS,
)
from tests.install_upgrade_operators.cert_renewal.utils import (
    SECRETS,
    get_certificates_validity_period_and_checkend_result,
)
from tests.install_upgrade_operators.constants import (
    HCO_CR_CERT_CONFIG_CA_KEY,
    HCO_CR_CERT_CONFIG_KEY,
    HCO_CR_CERT_CONFIG_SERVER_KEY,
)
from utilities.constants import TIMEOUT_1MIN, TIMEOUT_11MIN
from utilities.hco import update_custom_resource
from utilities.infra import is_bug_open


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
        list_resource_reconcile=[CDI, NetworkAddonsConfig],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture()
def initial_certificates_dates(
    admin_client, hco_namespace, tmpdir, secrets_with_non_closed_bugs
):
    LOGGER.info(
        "Delete secrets so that the cert-manager will create new ones with the updated certConfig"
    )
    for secret in SECRETS:
        Secret(name=secret, namespace=hco_namespace.name).delete(wait=True)

    for secret in SECRETS:
        Secret(name=secret, namespace=hco_namespace.name).wait(timeout=TIMEOUT_1MIN)

    LOGGER.info("Retrieve the certificates dates")
    return get_certificates_validity_period_and_checkend_result(
        hco_namespace_name=hco_namespace.name,
        tmpdir=tmpdir,
        secrets_to_skip=secrets_with_non_closed_bugs,
        seconds=TIMEOUT_11MIN,
    )


@pytest.fixture(scope="module")
def secrets_with_non_closed_bugs():
    bugzilla_component_name_dict = {
        2017415: "ssp-operator-service-cert",
        2017442: VIRT_TEMPLATE_VALIDATOR_CERTS,
    }
    return tuple(
        component_name
        for bug_id, component_name in bugzilla_component_name_dict.items()
        if is_bug_open(
            bug_id=bug_id,
        )
    )
