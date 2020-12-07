"""
 Draining node by Node Maintenance Operator
"""

import logging
import random
from contextlib import contextmanager
from subprocess import run

import pytest
from pytest_testconfig import config as py_config
from resources.node_maintenance import NodeMaintenance
from resources.pod import Pod
from resources.utils import TimeoutExpiredError, TimeoutSampler
from resources.virtual_machine import VirtualMachineInstanceMigration

from tests.compute import utils as compute_utils
from tests.compute.virt import utils as virt_utils
from tests.conftest import winrmcli_pod
from utilities import console
from utilities.infra import BUG_STATUS_CLOSED
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
)


LOGGER = logging.getLogger(__name__)


@contextmanager
def running_sleep_in_linux(vm_cli):
    process = "sleep 1000"
    with vm_cli as vm_console:
        vm_console.sendline(f"nohup {process} &")
        vm_console.expect("nohup: ")
    yield
    with vm_cli as vm_console:
        vm_console.sendline(f'ps aux | grep "{process}" | grep -v grep | wc -l')
        vm_console.expect("1")


@contextmanager
def node_mgmt_console(node, node_mgmt):
    try:
        LOGGER.info(f"{node_mgmt.capitalize()} the node {node.name}")
        extra_opts = (
            "--delete-local-data --ignore-daemonsets=true --force"
            if node_mgmt == "drain"
            else ""
        )
        run(
            f"nohup oc adm {node_mgmt} {node.name} {extra_opts} &",
            shell=True,
        )
        yield
    finally:
        LOGGER.info(f"Uncordon node {node.name}")
        run(f"oc adm uncordon {node.name}", shell=True)
        virt_utils.wait_for_node_schedulable_status(
            node=node,
            status=True,
        )


def drain_using_console(dyn_client, source_node, source_pod, vm, vm_cli):
    with running_sleep_in_linux(vm_cli=vm_cli):
        with node_mgmt_console(node=source_node, node_mgmt="drain"):
            check_draining_process(dyn_client=dyn_client, source_pod=source_pod, vm=vm)


def drain_using_console_windows(
    dyn_client,
    source_node,
    source_pod,
    vm,
    winrmcli_pod,
    helper_vm=False,
):
    process_name = "mspaint.exe"
    pre_migrate_processid = compute_utils.start_and_fetch_processid_on_windows_vm(
        vm=vm,
        winrmcli_pod=winrmcli_pod,
        process_name=process_name,
        helper_vm=helper_vm,
    )
    with node_mgmt_console(node=source_node, node_mgmt="drain"):
        check_draining_process(dyn_client=dyn_client, source_pod=source_pod, vm=vm)
        post_migrate_processid = compute_utils.fetch_processid_from_windows_vm(
            vm=vm,
            winrmcli_pod=winrmcli_pod,
            process_name=process_name,
            helper_vm=helper_vm,
        )
        assert (
            post_migrate_processid == pre_migrate_processid
        ), f"Post migrate processid is: {post_migrate_processid}. Pre migrate processid is: {pre_migrate_processid}"


def node_filter(pod, schedulable_nodes):
    nodes_for_winrmcli = list(
        filter(
            lambda node: node.name != pod.node.name,
            schedulable_nodes,
        )
    )
    assert len(nodes_for_winrmcli) > 0, "No available nodes."
    return nodes_for_winrmcli


@pytest.fixture()
def vm_container_disk_fedora(namespace, unprivileged_client):
    name = f"vm-nodemaintenance-{random.randrange(99999)}"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        eviction=True,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.fixture(scope="class")
def winrmcli_pod_nodeselector_scope_class(
    rhel7_workers,
    sa_ready,
    namespace,
    vm_instance_from_template_multi_storage_scope_class,
    schedulable_nodes,
):
    """Creates a Winrmcli Pod with a node selector."""
    # For RHEL7 workers, helper_vm is used
    if rhel7_workers:
        yield
    else:
        yield from winrmcli_pod(
            namespace=namespace,
            node_selector=node_filter(
                pod=vm_instance_from_template_multi_storage_scope_class.vmi.virt_launcher_pod,
                schedulable_nodes=schedulable_nodes,
            )[0].name,
        )


def assert_pod_status_completed(source_pod):
    source_pod.wait_for_status(status=Pod.Status.SUCCEEDED, timeout=180)
    assert (
        source_pod.instance.status.containerStatuses[0].state.terminated.reason
        == Pod.Status.COMPLETED
    )


def check_draining_process(dyn_client, source_pod, vm):
    source_node = source_pod.node
    LOGGER.info(f"The VMI was running on {source_node.name}")
    virt_utils.wait_for_node_schedulable_status(node=source_node, status=False)
    for migration_job in VirtualMachineInstanceMigration.get(
        dyn_client=dyn_client, namespace=vm.namespace
    ):
        if migration_job.instance.spec.vmiName == vm.name:
            migration_job.wait_for_status(
                status=migration_job.Status.SUCCEEDED, timeout=1800
            )
    assert_pod_status_completed(source_pod=source_pod)
    target_pod = vm.vmi.virt_launcher_pod
    target_pod.wait_for_status(status=Pod.Status.RUNNING, timeout=180)
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
def no_migration_job(admin_client, vm_instance_from_template_multi_storage_scope_class):
    migration_job = get_migration_job(
        dyn_client=admin_client,
        namespace=vm_instance_from_template_multi_storage_scope_class.namespace,
    )
    if migration_job:
        migration_job.delete(wait=True)


def migration_job_sampler(dyn_client, namespace):
    samples = TimeoutSampler(
        timeout=30,
        sleep=2,
        func=get_migration_job,
        dyn_client=dyn_client,
        namespace=namespace,
    )
    for sample in samples:
        if sample:
            return


@pytest.mark.bugzilla(
    1888790, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)
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
        vm_cli=console.Fedora(vm_container_disk_fedora),
    )


@pytest.mark.bugzilla(
    1888790, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_class, vm_instance_from_template_multi_storage_scope_class",
    [
        pytest.param(
            {
                "dv_name": "dv-rhel8-template-node-maintenance",
                "image": py_config["latest_rhel_version"]["image_path"],
                "dv_size": py_config["latest_rhel_version"]["dv_size"],
            },
            {
                "vm_name": "rhel8-template-node-maintenance",
                "template_labels": py_config["latest_rhel_version"]["template_labels"],
                "set_vm_common_cpu": True,
            },
        )
    ],
    indirect=True,
)
@pytest.mark.usefixtures(
    "skip_when_one_node",
    "skip_access_mode_rwo_scope_class",
    "data_volume_multi_storage_scope_class",
)
class TestNodeMaintenanceRHEL:
    @pytest.mark.polarion("CNV-2286")
    def test_node_maintenance_job_rhel(
        self,
        no_migration_job,
        vm_instance_from_template_multi_storage_scope_class,
        admin_client,
    ):
        source_pod = (
            vm_instance_from_template_multi_storage_scope_class.vmi.virt_launcher_pod
        )
        source_node = source_pod.node

        with running_sleep_in_linux(
            vm_cli=console.RHEL(vm=vm_instance_from_template_multi_storage_scope_class)
        ):
            with NodeMaintenance(
                name="node-maintenance-job", node=source_node, timeout=600
            ) as nm:
                nm.wait_for_status(status=nm.Status.RUNNING)
                check_draining_process(
                    dyn_client=admin_client,
                    source_pod=source_pod,
                    vm=vm_instance_from_template_multi_storage_scope_class,
                )
                nm.wait_for_status(status=nm.Status.SUCCEEDED, timeout=360)
            virt_utils.wait_for_node_schedulable_status(node=source_node, status=True)

    @pytest.mark.polarion("CNV-2292")
    def test_node_drain_using_console_rhel(
        self,
        no_migration_job,
        vm_instance_from_template_multi_storage_scope_class,
        admin_client,
    ):
        drain_using_console(
            dyn_client=admin_client,
            source_node=vm_instance_from_template_multi_storage_scope_class.vmi.virt_launcher_pod.node,
            source_pod=vm_instance_from_template_multi_storage_scope_class.vmi.virt_launcher_pod,
            vm=vm_instance_from_template_multi_storage_scope_class,
            vm_cli=console.RHEL(vm=vm_instance_from_template_multi_storage_scope_class),
        )

    @pytest.mark.polarion("CNV-4995")
    def test_migration_when_multiple_nodes_unschedulable_using_console_rhel(
        self,
        no_migration_job,
        vm_instance_from_template_multi_storage_scope_class,
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
        vm = vm_instance_from_template_multi_storage_scope_class
        cordon_nodes = node_filter(
            pod=vm.vmi.virt_launcher_pod,
            schedulable_nodes=schedulable_nodes,
        )
        with node_mgmt_console(node=cordon_nodes[0], node_mgmt="cordon"):
            drain_using_console(
                dyn_client=admin_client,
                source_node=vm_instance_from_template_multi_storage_scope_class.vmi.virt_launcher_pod.node,
                source_pod=vm_instance_from_template_multi_storage_scope_class.vmi.virt_launcher_pod,
                vm=vm_instance_from_template_multi_storage_scope_class,
                vm_cli=console.RHEL(
                    vm=vm_instance_from_template_multi_storage_scope_class
                ),
            )


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_class, vm_instance_from_template_multi_storage_scope_class",
    [
        pytest.param(
            {
                "dv_name": "dv-win-template-node-cordon-and-drain",
                "image": py_config["latest_windows_version"]["image_path"],
                "dv_size": py_config["latest_windows_version"]["dv_size"],
            },
            {
                "vm_name": "wind-template-node-cordon-and-drain",
                "template_labels": py_config["latest_windows_version"][
                    "template_labels"
                ],
                "cpu_threads": 2,
                "set_vm_common_cpu": True,
            },
        ),
    ],
    indirect=True,
)
@pytest.mark.usefixtures(
    "skip_when_one_node",
    "skip_access_mode_rwo_scope_class",
    "data_volume_multi_storage_scope_class",
)
class TestNodeCordonAndDrain:
    @pytest.mark.bugzilla(
        1888790, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    @pytest.mark.polarion("CNV-2048")
    def test_node_drain_template_windows(
        self,
        no_migration_job,
        vm_instance_from_template_multi_storage_scope_class,
        winrmcli_pod_nodeselector_scope_class,
        bridge_attached_helper_vm,
        admin_client,
    ):
        vm = vm_instance_from_template_multi_storage_scope_class
        drain_using_console_windows(
            dyn_client=admin_client,
            source_node=vm.vmi.virt_launcher_pod.node,
            source_pod=vm.vmi.virt_launcher_pod,
            vm=vm,
            winrmcli_pod=winrmcli_pod_nodeselector_scope_class,
            helper_vm=bridge_attached_helper_vm,
        )

    @pytest.mark.polarion("CNV-4906")
    def test_node_cordon_template_windows(
        self,
        no_migration_job,
        vm_instance_from_template_multi_storage_scope_class,
        admin_client,
    ):
        vm = vm_instance_from_template_multi_storage_scope_class
        with node_mgmt_console(node=vm.vmi.virt_launcher_pod.node, node_mgmt="cordon"):
            with pytest.raises(TimeoutExpiredError):
                migration_job_sampler(
                    dyn_client=admin_client,
                    namespace=vm.namespace,
                )
                pytest.fail("Cordon of a Node should not trigger VMI migration.")
