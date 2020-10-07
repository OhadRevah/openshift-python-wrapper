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
from resources.virtual_machine import VirtualMachineInstanceMigration
from tests.compute import utils as compute_utils
from tests.compute.virt import utils as virt_utils
from tests.conftest import winrmcli_pod
from utilities import console
from utilities.infra import Images
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
            "--delete-local-data --ignore-daemonsets=true"
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
    source_pod.wait_deleted()
    target_node = vm.vmi.virt_launcher_pod.node
    LOGGER.info(f"The VMI is currently running on {target_node.name}")
    assert (
        target_node != source_node
    ), f"Source Node: {source_node.name} and Target Node: {target_node.name} should be different"


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


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_class, vm_instance_from_template_multi_storage_scope_class",
    [
        pytest.param(
            {
                "dv_name": "dv-rhel8-template-node-maintenance",
                "image": f"{Images.Rhel.DIR}/{Images.Rhel.RHEL8_0_IMG}",
                "dv_size": Images.Rhel.DEFAULT_DV_SIZE,
            },
            {
                "vm_name": "rhel8-template-node-maintenance",
                "template_labels": {
                    "os": "rhel8.0",
                    "workload": "server",
                    "flavor": "tiny",
                },
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
        self, vm_instance_from_template_multi_storage_scope_class, admin_client
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
        self, vm_instance_from_template_multi_storage_scope_class, admin_client
    ):
        drain_using_console(
            dyn_client=admin_client,
            source_node=vm_instance_from_template_multi_storage_scope_class.vmi.virt_launcher_pod.node,
            source_pod=vm_instance_from_template_multi_storage_scope_class.vmi.virt_launcher_pod,
            vm=vm_instance_from_template_multi_storage_scope_class,
            vm_cli=console.RHEL(vm=vm_instance_from_template_multi_storage_scope_class),
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
    @pytest.mark.polarion("CNV-2048")
    def test_node_drain_template_windows(
        self,
        vm_instance_from_template_multi_storage_scope_class,
        winrmcli_pod_nodeselector_scope_class,
        bridge_attached_helper_vm,
        admin_client,
    ):
        drain_using_console_windows(
            dyn_client=admin_client,
            source_node=vm_instance_from_template_multi_storage_scope_class.vmi.virt_launcher_pod.node,
            source_pod=vm_instance_from_template_multi_storage_scope_class.vmi.virt_launcher_pod,
            vm=vm_instance_from_template_multi_storage_scope_class,
            winrmcli_pod=winrmcli_pod_nodeselector_scope_class,
            helper_vm=bridge_attached_helper_vm,
        )
