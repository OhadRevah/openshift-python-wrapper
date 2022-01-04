import logging

import pytest

from tests.compute.ssp.descheduler.utils import (
    verify_running_process_after_failover,
    verify_vms_consistent_virt_launcher_pods,
    verify_vms_distribution_after_failover,
)


LOGGER = logging.getLogger(__name__)
TESTS_CLASS_NAME = "TestDeschedulerEvictsVMAfterDrainUncordon"


pytestmark = [pytest.mark.tier3]


@pytest.mark.usefixtures(
    "skip_if_1tb_memory_or_more_node",
    "skip_when_one_node",
)
class TestDeschedulerEvictsVMAfterDrainUncordon:
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::test_descheduler_evicts_vm_after_drain_uncordon"
    )
    @pytest.mark.polarion("CNV-5922")
    def test_descheduler_evicts_vm_after_drain_uncordon(
        self,
        updated_descheduler,
        descheduler_pod,
        deployed_vms,
        vms_started_process,
        node_to_drain,
        drain_uncordon_node,
        schedulable_nodes,
    ):
        verify_vms_distribution_after_failover(
            vms=deployed_vms, nodes=schedulable_nodes
        )

    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::test_no_migrations_storm",
        depends=[
            f"{TESTS_CLASS_NAME}::test_descheduler_evicts_vm_after_drain_uncordon"
        ],
    )
    @pytest.mark.polarion("CNV-7316")
    def test_no_migrations_storm(
        self,
        deployed_vms,
        downscaled_descheduler_cluster_deployment,
        completed_migrations,
    ):
        LOGGER.info(
            "Verify no migration storm after triggered migrations by the descheduler."
        )
        verify_vms_consistent_virt_launcher_pods(running_vms=deployed_vms)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::test_no_migrations_storm"])
    @pytest.mark.polarion("CNV-8288")
    def test_running_process_after_migrations_complete(
        self,
        deployed_vms,
        vms_started_process,
    ):
        verify_running_process_after_failover(
            vms_list=deployed_vms, process_dict=vms_started_process
        )
