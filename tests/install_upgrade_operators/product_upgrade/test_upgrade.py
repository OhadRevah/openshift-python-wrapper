import logging

import pytest

import tests.install_upgrade_operators.product_upgrade.utils as upgrade_utils
from utilities.constants import (
    DEPENDENCY_SCOPE_SESSION,
    UPGRADE_TEST_DEPENDNCY_NODE_ID,
    UPGRADE_TEST_ORDERING_NODE_ID,
)
from utilities.infra import validate_nodes_ready, validate_nodes_schedulable


LOGGER = logging.getLogger(__name__)


@pytest.mark.upgrade
@pytest.mark.usefixtures(
    "skip_when_one_node",
    "cnv_upgrade_path",
    "nodes_taints_before_upgrade",
    "nodes_labels_before_upgrade",
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
                ocp_channel=pytestconfig.option.ocp_channel,
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

    @pytest.mark.polarion("CNV-4509")
    @pytest.mark.order(after=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[UPGRADE_TEST_DEPENDNCY_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_cnv_pods_running_after_upgrade(self, admin_client, hco_namespace):
        LOGGER.info("Verify CNV pods running after upgrade.")
        upgrade_utils.verify_cnv_pods_are_running(
            dyn_client=admin_client, hco_namespace=hco_namespace
        )

    @pytest.mark.polarion("CNV-4510")
    @pytest.mark.order(after=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[UPGRADE_TEST_DEPENDNCY_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_nodes_ready_after_upgrade(self, nodes):
        LOGGER.info("Verify all nodes are in ready state after upgrade")
        validate_nodes_ready(nodes=nodes)

    @pytest.mark.polarion("CNV-6865")
    @pytest.mark.order(after=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[UPGRADE_TEST_DEPENDNCY_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_nodes_schedulable_after_upgrade(
        self,
        nodes,
    ):
        LOGGER.info("Verify all nodes are in schedulable state after upgrade")
        validate_nodes_schedulable(nodes=nodes)

    @pytest.mark.polarion("CNV-6866")
    @pytest.mark.order(after=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[UPGRADE_TEST_DEPENDNCY_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_nodes_taints_after_upgrade(
        self, admin_client, nodes, nodes_taints_before_upgrade
    ):
        LOGGER.info("Verify nodes taints after upgrade.")
        upgrade_utils.verify_nodes_taints_after_upgrade(
            nodes=nodes, nodes_taints_before_upgrade=nodes_taints_before_upgrade
        )

    @pytest.mark.polarion("CNV-6924")
    @pytest.mark.order(after=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[UPGRADE_TEST_DEPENDNCY_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_nodes_labels_after_upgrade(
        self, admin_client, nodes, nodes_labels_before_upgrade
    ):
        LOGGER.info("Verify nodes labels after upgrade.")
        upgrade_utils.verify_nodes_labels_after_upgrade(
            nodes=nodes, nodes_labels_before_upgrade=nodes_labels_before_upgrade
        )
