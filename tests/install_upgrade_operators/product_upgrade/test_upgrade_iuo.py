import logging

import pytest

from tests.install_upgrade_operators.product_upgrade.utils import (
    verify_cnv_pods_are_running,
    verify_nodes_labels_after_upgrade,
    verify_nodes_taints_after_upgrade,
)
from utilities.constants import (
    DEPENDENCY_SCOPE_SESSION,
    UPGRADE_TEST_DEPENDNCY_NODE_ID,
    UPGRADE_TEST_ORDERING_NODE_ID,
)
from utilities.infra import validate_nodes_ready, validate_nodes_schedulable


LOGGER = logging.getLogger(__name__)


pytestmark = pytest.mark.usefixtures(
    "skip_when_one_node",
    "cnv_upgrade_path",
    "nodes_taints_before_upgrade",
    "nodes_labels_before_upgrade",
)


@pytest.mark.upgrade
class TestUpgradeIUO:
    """Post-upgrade tests"""

    @pytest.mark.polarion("CNV-4509")
    @pytest.mark.order(after=UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[UPGRADE_TEST_DEPENDNCY_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_cnv_pods_running_after_upgrade(self, admin_client, hco_namespace):
        LOGGER.info("Verify CNV pods running after upgrade.")
        verify_cnv_pods_are_running(
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
        verify_nodes_taints_after_upgrade(
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
        verify_nodes_labels_after_upgrade(
            nodes=nodes, nodes_labels_before_upgrade=nodes_labels_before_upgrade
        )
