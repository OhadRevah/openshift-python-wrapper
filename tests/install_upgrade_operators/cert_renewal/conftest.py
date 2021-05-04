import logging

import pytest

from utilities.hco import (
    DEFAULT_HCO_PROGRESSING_CONDITIONS,
    modify_hco_cr,
    wait_for_hco_conditions,
)


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
    backup = modify_hco_cr(
        patch={"spec": {"certConfig": target_certconfig_stanza}},
        hco=hyperconverged_resource_scope_class,
    )
    LOGGER.info("Waiting for HCO to report progressing condition")
    wait_for_hco_conditions(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        expected_conditions=DEFAULT_HCO_PROGRESSING_CONDITIONS,
    )
    LOGGER.info(
        "Waiting for all HCO conditions to detect that it's back to a stable configuration"
    )
    wait_for_hco_conditions(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        consecutive_checks_count=6,
    )
    yield
    LOGGER.info("Restoring certconfig in HCO CR")
    modify_hco_cr(
        patch=backup[hyperconverged_resource_scope_class],
        hco=hyperconverged_resource_scope_class,
    )
