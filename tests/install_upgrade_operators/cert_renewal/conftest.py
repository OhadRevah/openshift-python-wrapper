import logging

import pytest

from utilities.constants import TIMEOUT_1MIN
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
    target_certconfig_stanza = {"ca": {**request.param}, "server": {**request.param}}
    LOGGER.info("Modifying certconfig in HCO CR")
    with update_custom_resource(
        patch={
            hyperconverged_resource_scope_class: {
                "spec": {"certConfig": target_certconfig_stanza}
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
