import logging
import os

import pytest

from tests.install_upgrade_operators.product_upgrade.utils import (
    process_alerts_fired_during_upgrade,
    verify_cnv_pods_are_running,
    verify_nodes_labels_after_upgrade,
    verify_nodes_taints_after_upgrade,
)
from tests.upgrade_params import (
    COMPUTE_VMS_RUNNING_AFTER_UPGRADE_TEST_NODE_ID,
    IUO_CNV_POD_ORDERING_NODE_ID,
    IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
)
from utilities.constants import DEPENDENCY_SCOPE_SESSION
from utilities.infra import validate_nodes_ready, validate_nodes_schedulable


LOGGER = logging.getLogger(__name__)

pytestmark = pytest.mark.usefixtures(
    "nodes_taints_before_upgrade",
    "nodes_labels_before_upgrade",
)

DEPENDENCIES_NODE_ID_PREFIX = f"{os.path.abspath(__file__)}::TestUpgradeIUO"

NODE_READY_ORDERING_NODE_ID = (
    f"{DEPENDENCIES_NODE_ID_PREFIX}::test_nodes_ready_after_upgrade"
)


@pytest.mark.sno
@pytest.mark.upgrade
class TestUpgradeIUO:
    """Post-upgrade tests"""

    @pytest.mark.polarion("CNV-9081")
    @pytest.mark.order(before=IUO_CNV_POD_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_alerts_fired_during_ocp_upgrade(
        self, skip_on_cnv_upgrade, prometheus, fired_alerts_during_ocp_upgrade
    ):
        LOGGER.info("Verify if any alerts were fired during ocp upgrades")
        process_alerts_fired_during_upgrade(
            prometheus=prometheus,
            fired_alerts_during_upgrade=fired_alerts_during_ocp_upgrade,
        )

        assert not fired_alerts_during_ocp_upgrade, (
            f"Following alerts were fired during ocp upgrade:"
            f" {fired_alerts_during_ocp_upgrade}"
        )

    @pytest.mark.polarion("CNV-9079")
    @pytest.mark.order(before=IUO_CNV_POD_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_cnv_alerts_fired_during_cnv_upgrade(
        self, skip_on_ocp_upgrade, prometheus, fired_alerts_during_cnv_upgrade
    ):
        process_alerts_fired_during_upgrade(
            prometheus=prometheus,
            fired_alerts_during_upgrade=fired_alerts_during_cnv_upgrade,
        )

        assert (
            not fired_alerts_during_cnv_upgrade
        ), f"Following alerts were fired during upgrade: {fired_alerts_during_cnv_upgrade}"

    @pytest.mark.polarion("CNV-4509")
    @pytest.mark.order(before=COMPUTE_VMS_RUNNING_AFTER_UPGRADE_TEST_NODE_ID)
    @pytest.mark.dependency(
        name=IUO_CNV_POD_ORDERING_NODE_ID,
        depends=[IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_cnv_pods_running_after_upgrade(self, admin_client, hco_namespace):
        LOGGER.info("Verify CNV pods running after upgrade.")
        verify_cnv_pods_are_running(
            dyn_client=admin_client, hco_namespace=hco_namespace
        )

    @pytest.mark.polarion("CNV-4510")
    @pytest.mark.order(before=COMPUTE_VMS_RUNNING_AFTER_UPGRADE_TEST_NODE_ID)
    @pytest.mark.dependency(
        name=NODE_READY_ORDERING_NODE_ID,
        depends=[IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID, IUO_CNV_POD_ORDERING_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_nodes_ready_after_upgrade(self, nodes):
        LOGGER.info("Verify all nodes are in ready state after upgrade")
        validate_nodes_ready(nodes=nodes)

    @pytest.mark.polarion("CNV-6865")
    @pytest.mark.order(before=COMPUTE_VMS_RUNNING_AFTER_UPGRADE_TEST_NODE_ID)
    @pytest.mark.dependency(
        depends=[IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID, NODE_READY_ORDERING_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_nodes_schedulable_after_upgrade(
        self,
        nodes,
    ):
        LOGGER.info("Verify all nodes are in schedulable state after upgrade")
        validate_nodes_schedulable(nodes=nodes)

    @pytest.mark.polarion("CNV-6866")
    @pytest.mark.order(before=COMPUTE_VMS_RUNNING_AFTER_UPGRADE_TEST_NODE_ID)
    @pytest.mark.dependency(
        depends=[IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID, NODE_READY_ORDERING_NODE_ID],
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
    @pytest.mark.order(before=COMPUTE_VMS_RUNNING_AFTER_UPGRADE_TEST_NODE_ID)
    @pytest.mark.dependency(
        depends=[IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID, NODE_READY_ORDERING_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_nodes_labels_after_upgrade(
        self,
        admin_client,
        nodes,
        nodes_labels_before_upgrade,
        cnv_upgrade,
    ):
        LOGGER.info("Verify nodes labels after upgrade.")
        verify_nodes_labels_after_upgrade(
            nodes=nodes,
            nodes_labels_before_upgrade=nodes_labels_before_upgrade,
            cnv_upgrade=cnv_upgrade,
        )
