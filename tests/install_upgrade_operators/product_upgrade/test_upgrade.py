import logging

import pytest

import tests.install_upgrade_operators.product_upgrade.utils as upgrade_utils
from utilities.constants import UPGRADE_TEST_DEPENDNCY_NODE_ID


LOGGER = logging.getLogger(__name__)


@pytest.mark.upgrade
@pytest.mark.usefixtures(
    "skip_when_one_node",
    "cnv_upgrade_path",
)
class TestUpgrade:
    @pytest.mark.upgrade_resilience
    @pytest.mark.polarion("CNV-2991")
    @pytest.mark.dependency(name=UPGRADE_TEST_DEPENDNCY_NODE_ID)
    def test_upgrade_process(
        self,
        pytestconfig,
        admin_client,
        hco_namespace,
        hco_target_version,
        hco_current_version,
        cnv_upgrade_path,
        operatorhub_without_default_sources,
        cnv_registry_source,
        update_image_content_source,
        cnv_source,
        cnv_target_version,
    ):
        if pytestconfig.option.upgrade == "ocp":
            upgrade_utils.upgrade_ocp(
                ocp_image=pytestconfig.option.ocp_image,
                dyn_client=admin_client,
            )

        if pytestconfig.option.upgrade == "cnv":
            upgrade_utils.upgrade_cnv(
                dyn_client=admin_client,
                hco_namespace=hco_namespace,
                hco_target_version=hco_target_version,
                hco_current_version=hco_current_version,
                image=pytestconfig.option.cnv_image,
                cnv_upgrade_path=cnv_upgrade_path,
                upgrade_resilience=pytestconfig.option.upgrade_resilience,
                cnv_subscription_source=cnv_registry_source["cnv_subscription_source"],
                cnv_source=cnv_source,
                cnv_target_version=cnv_target_version,
            )
