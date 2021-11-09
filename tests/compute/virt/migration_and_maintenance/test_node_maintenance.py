"""
 Draining node by Node Maintenance Operator
"""

import logging
import random

import pytest
from ocp_resources.node_maintenance import NodeMaintenance
from ocp_resources.pod import Pod
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from ocp_resources.virtual_machine_instance_migration import (
    VirtualMachineInstanceMigration,
)

from tests.compute import utils as compute_utils
from tests.compute.virt import utils as virt_utils
from tests.os_params import (
    RHEL_LATEST,
    RHEL_LATEST_LABELS,
    RHEL_LATEST_OS,
    WINDOWS_LATEST,
    WINDOWS_LATEST_LABELS,
    WINDOWS_LATEST_OS,
)
from utilities.constants import (
    TIMEOUT_3MIN,
    TIMEOUT_6MIN,
    TIMEOUT_10MIN,
    TIMEOUT_30MIN,
    TIMEOUT_30SEC,
)
from utilities.infra import get_bug_status
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    node_mgmt_console,
    running_vm,
    wait_for_node_schedulable_status,
)


pytestmark = pytest.mark.post_upgrade


LOGGER = logging.getLogger(__name__)


def drain_using_console(dyn_client, source_node, source_pod, vm):
    with virt_utils.running_sleep_in_linux(vm=vm):
        with node_mgmt_console(node=source_node, node_mgmt="drain"):
            check_draining_process(dyn_client=dyn_client, source_pod=source_pod, vm=vm)


def drain_using_console_windows(
    dyn_client,
    source_node,
    source_pod,
    vm,
):
    process_name = "mspaint.exe"
    pre_migrate_processid = compute_utils.start_and_fetch_processid_on_windows_vm(
        vm=vm,
        process_name=process_name,
    )
    with node_mgmt_console(node=source_node, node_mgmt="drain"):
        check_draining_process(dyn_client=dyn_client, source_pod=source_pod, vm=vm)
        post_migrate_processid = compute_utils.fetch_processid_from_windows_vm(
            vm=vm,
            process_name=process_name,
        )
        assert (
            post_migrate_processid == pre_migrate_processid
        ), f"Post migrate processid is: {post_migrate_processid}. Pre migrate processid is: {pre_migrate_processid}"


def node_filter(pod, schedulable_nodes):
    nodes_for_test = list(
        filter(
            lambda node: node.name != pod.node.name,
            schedulable_nodes,
        )
    )
    assert len(nodes_for_test) > 0, "No available nodes."
    return nodes_for_test


@pytest.fixture()
def vm_container_disk_fedora(
    cluster_cpu_model_scope_module,
    namespace,
    unprivileged_client,
):
    name = f"vm-nodemaintenance-{random.randrange(99999)}"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        eviction=True,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
    ) as vm:
        running_vm(vm=vm)
        yield vm


def assert_pod_status_completed(source_pod):
    # TODO: remove TimeoutExpiredError exception once bug 1943164 is resolved
    try:
        source_pod.wait_for_status(status=Pod.Status.SUCCEEDED, timeout=TIMEOUT_3MIN)
        assert (
            source_pod.instance.status.containerStatuses[0].state.terminated.reason
            == Pod.Status.COMPLETED
        )
    except TimeoutExpiredError:
        if get_bug_status(
            bug=1943164,
        ):
            source_pod.wait_for_status(status=Pod.Status.FAILED, timeout=TIMEOUT_3MIN)
        else:
            raise


def check_draining_process(dyn_client, source_pod, vm):
    source_node = source_pod.node
    LOGGER.info(f"The VMI was running on {source_node.name}")
    wait_for_node_schedulable_status(node=source_node, status=False)
    for migration_job in VirtualMachineInstanceMigration.get(
        dyn_client=dyn_client, namespace=vm.namespace
    ):
        if migration_job.instance.spec.vmiName == vm.name:
            migration_job.wait_for_status(
                status=migration_job.Status.SUCCEEDED, timeout=TIMEOUT_30MIN
            )
    assert_pod_status_completed(source_pod=source_pod)
    target_pod = vm.vmi.virt_launcher_pod
    target_pod.wait_for_status(status=Pod.Status.RUNNING, timeout=TIMEOUT_3MIN)
    target_node = target_pod.node
    LOGGER.info(f"The VMI is currently running on {target_node.name}")
    assert (
        target_node != source_node
    ), f"Source Node: {source_node.name} and Target Node: {target_node.name} should be different"


def get_migration_job(dyn_client, namespace):
    for migration_job in VirtualMachineInstanceMigration.get(
        dyn_client=dyn_client, namespace=namespace
    ):
        return migration_job


@pytest.fixture()
def no_migration_job(
    admin_client, golden_image_vm_instance_from_template_multi_storage_scope_class
):
    migration_job = get_migration_job(
        dyn_client=admin_client,
        namespace=golden_image_vm_instance_from_template_multi_storage_scope_class.namespace,
    )
    if migration_job:
        migration_job.delete(wait=True)


def migration_job_sampler(dyn_client, namespace):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_30SEC,
        sleep=2,
        func=get_migration_job,
        dyn_client=dyn_client,
        namespace=namespace,
    )
    for sample in samples:
        if sample:
            return


@pytest.mark.polarion("CNV-3006")
def test_node_drain_using_console_fedora(
    skip_when_one_node,
    admin_client,
    vm_container_disk_fedora,
):

    drain_using_console(
        dyn_client=admin_client,
        source_node=vm_container_disk_fedora.vmi.virt_launcher_pod.node,
        source_pod=vm_container_disk_fedora.vmi.virt_launcher_pod,
        vm=vm_container_disk_fedora,
    )


@pytest.mark.parametrize(
    "golden_image_data_volume_multi_storage_scope_class,"
    "golden_image_vm_instance_from_template_multi_storage_scope_class",
    [
        pytest.param(
            {
                "dv_name": RHEL_LATEST_OS,
                "image": RHEL_LATEST["image_path"],
                "dv_size": RHEL_LATEST["dv_size"],
            },
            {
                "vm_name": "rhel8-template-node-maintenance",
                "template_labels": RHEL_LATEST_LABELS,
            },
        )
    ],
    indirect=True,
)
@pytest.mark.usefixtures(
    "skip_when_one_node",
    "skip_access_mode_rwo_scope_class",
    "cluster_cpu_model_scope_class",
    "golden_image_data_volume_multi_storage_scope_class",
)
@pytest.mark.ibm_bare_metal
class TestNodeMaintenanceRHEL:
    @pytest.mark.polarion("CNV-2286")
    def test_node_maintenance_job_rhel(
        self,
        no_migration_job,
        golden_image_vm_instance_from_template_multi_storage_scope_class,
        admin_client,
    ):
        source_pod = (
            golden_image_vm_instance_from_template_multi_storage_scope_class.vmi.virt_launcher_pod
        )
        source_node = source_pod.node

        with virt_utils.running_sleep_in_linux(
            vm=golden_image_vm_instance_from_template_multi_storage_scope_class
        ):
            with NodeMaintenance(
                name="node-maintenance-job", node=source_node, timeout=TIMEOUT_10MIN
            ) as nm:
                nm.wait_for_status(status=nm.Status.RUNNING)
                check_draining_process(
                    dyn_client=admin_client,
                    source_pod=source_pod,
                    vm=golden_image_vm_instance_from_template_multi_storage_scope_class,
                )
                nm.wait_for_status(status=nm.Status.SUCCEEDED, timeout=TIMEOUT_6MIN)
            wait_for_node_schedulable_status(node=source_node, status=True)

    @pytest.mark.polarion("CNV-2292")
    def test_node_drain_using_console_rhel(
        self,
        no_migration_job,
        golden_image_vm_instance_from_template_multi_storage_scope_class,
        admin_client,
    ):
        drain_using_console(
            dyn_client=admin_client,
            source_node=golden_image_vm_instance_from_template_multi_storage_scope_class.vmi.virt_launcher_pod.node,
            source_pod=golden_image_vm_instance_from_template_multi_storage_scope_class.vmi.virt_launcher_pod,
            vm=golden_image_vm_instance_from_template_multi_storage_scope_class,
        )

    @pytest.mark.polarion("CNV-4995")
    def test_migration_when_multiple_nodes_unschedulable_using_console_rhel(
        self,
        no_migration_job,
        golden_image_vm_instance_from_template_multi_storage_scope_class,
        schedulable_nodes,
        admin_client,
    ):
        """Test VMI migration, when multiple nodes are unschedulable.

        In our BM or PSI setups, we mostly use only 3 worker nodes,
        the OCS pods would need at-least 2 nodes up and running, to
        avoid violation of the ceph pod's disruption budget.
        Hence we simulating this case here, with Cordon 1 node and
        Drain 1 node, instead of Draining 2 Worker nodes.

        1. Start a VMI
        2. Cordon a Node, other than the current running VMI Node.
        3. Drain the Node, on which the VMI is present.
        4. Make sure the VMI is migrated to the other node.
        """
        vm = golden_image_vm_instance_from_template_multi_storage_scope_class
        cordon_nodes = node_filter(
            pod=vm.vmi.virt_launcher_pod,
            schedulable_nodes=schedulable_nodes,
        )
        with node_mgmt_console(node=cordon_nodes[0], node_mgmt="cordon"):
            drain_using_console(
                dyn_client=admin_client,
                source_node=golden_image_vm_instance_from_template_multi_storage_scope_class.vmi.virt_launcher_pod.node,
                source_pod=golden_image_vm_instance_from_template_multi_storage_scope_class.vmi.virt_launcher_pod,
                vm=golden_image_vm_instance_from_template_multi_storage_scope_class,
            )


@pytest.mark.parametrize(
    "golden_image_data_volume_multi_storage_scope_class,"
    "golden_image_vm_instance_from_template_multi_storage_scope_class",
    [
        pytest.param(
            {
                "dv_name": WINDOWS_LATEST_OS,
                "image": WINDOWS_LATEST["image_path"],
                "dv_size": WINDOWS_LATEST["dv_size"],
            },
            {
                "vm_name": "wind-template-node-cordon-and-drain",
                "template_labels": WINDOWS_LATEST_LABELS,
            },
        ),
    ],
    indirect=True,
)
@pytest.mark.usefixtures(
    "skip_when_one_node",
    "skip_access_mode_rwo_scope_class",
    "cluster_cpu_model_scope_class",
    "golden_image_data_volume_multi_storage_scope_class",
)
@pytest.mark.ibm_bare_metal
class TestNodeCordonAndDrain:
    @pytest.mark.polarion("CNV-2048")
    def test_node_drain_template_windows(
        self,
        no_migration_job,
        golden_image_vm_instance_from_template_multi_storage_scope_class,
        admin_client,
    ):
        vm = golden_image_vm_instance_from_template_multi_storage_scope_class
        drain_using_console_windows(
            dyn_client=admin_client,
            source_node=vm.vmi.virt_launcher_pod.node,
            source_pod=vm.vmi.virt_launcher_pod,
            vm=vm,
        )

    @pytest.mark.polarion("CNV-4906")
    def test_node_cordon_template_windows(
        self,
        no_migration_job,
        golden_image_vm_instance_from_template_multi_storage_scope_class,
        admin_client,
    ):
        vm = golden_image_vm_instance_from_template_multi_storage_scope_class
        with node_mgmt_console(node=vm.vmi.virt_launcher_pod.node, node_mgmt="cordon"):
            with pytest.raises(TimeoutExpiredError):
                migration_job_sampler(
                    dyn_client=admin_client,
                    namespace=vm.namespace,
                )
                pytest.fail("Cordon of a Node should not trigger VMI migration.")
