import logging

import pytest

from tests.install_upgrade_operators.product_upgrade.utils import (
    upgrade_cnv,
    upgrade_ocp,
)
from tests.upgrade_params import UPGRADE_TEST_DEPENDENCY_NODE_ID


LOGGER = logging.getLogger(__name__)


@pytest.mark.upgrade
@pytest.mark.usefixtures("skip_when_one_node")
class TestUpgrade:
    @pytest.mark.ocp_upgrade
    @pytest.mark.upgrade_resilience
    @pytest.mark.polarion("CNV-8381")
    @pytest.mark.dependency(name=UPGRADE_TEST_DEPENDENCY_NODE_ID)
    def test_ocp_upgrade_process(
        self,
        pytestconfig,
        admin_client,
    ):
        upgrade_ocp(
            ocp_image=pytestconfig.option.ocp_image,
            dyn_client=admin_client,
        )

    @pytest.mark.cnv_upgrade
    @pytest.mark.upgrade_resilience
    @pytest.mark.polarion("CNV-2991")
    @pytest.mark.dependency(name=UPGRADE_TEST_DEPENDENCY_NODE_ID)
    def test_cnv_upgrade_process(
        self,
        pytestconfig,
        admin_client,
        hco_namespace,
        hco_target_version,
        hco_current_version,
        cnv_upgrade_path,
        disabled_default_sources_in_operatorhub,
        cnv_registry_source,
        update_image_content_source,
        is_deployment_from_production_source,
        cnv_target_version,
        cnv_subscription_scope_session,
    ):
        LOGGER.info(f"CNV upgrade: {cnv_upgrade_path}")
        upgrade_cnv(
            dyn_client=admin_client,
            hco_namespace=hco_namespace,
            hco_target_version=hco_target_version,
            hco_current_version=hco_current_version,
            cnv_target_image=pytestconfig.option.cnv_image,
            upgrade_resilience=pytestconfig.option.upgrade_resilience,
            cnv_subscription_source=cnv_registry_source["cnv_subscription_source"],
            is_deployment_from_production_source=is_deployment_from_production_source,
            cnv_target_version=cnv_target_version,
            cnv_subscription=cnv_subscription_scope_session,
        )
