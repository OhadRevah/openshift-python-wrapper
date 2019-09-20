"""
 Draining node by Node Maintenance Operator
"""

import logging
import random
from contextlib import contextmanager
from subprocess import run

import pytest
from resources.node_maintenance import NodeMaintenance
from resources.template import Template
from resources.utils import TimeoutSampler
from resources.virtual_machine import (
    VirtualMachineInstance,
    VirtualMachineInstanceMigration,
)
from tests.compute.utils import WinRMcliPod
from tests.compute.virt import utils as virt_utils
from utilities import console
from utilities.infra import create_ns
from utilities.storage import DataVolumeTestResource
from utilities.virt import (
    VirtualMachineForTests,
    VirtualMachineForTestsFromTemplate,
    fedora_vm_body,
)


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module", autouse=True)
def node_maintenance_ns(unprivileged_client):
    yield from create_ns(client=unprivileged_client, name="node-maintenance-ns")


@contextmanager
def running_sleep_in_fedora(vm):
    process = "sleep 1000"
    with console.Fedora(vm) as vm_console:
        vm_console.sendline(f"nohup {process} &")
        vm_console.expect("nohup: ")
    yield
    with console.Fedora(vm) as vm_console:
        vm_console.sendline(f'ps aux | grep "{process}" | grep -v grep | wc -l')
        vm_console.expect("1")


@contextmanager
def drain_node_console(node):
    try:
        run(
            f"nohup oc adm drain {node.name} --delete-local-data --ignore-daemonsets=true --force &",
            shell=True,
        )
        yield
    finally:
        run(f"oc adm uncordon {node.name}", shell=True)


@pytest.fixture(scope="module")
def skip_when_other_vmi_present(default_client):
    if list(VirtualMachineInstance.get(default_client)):
        pytest.skip(msg="Can't work when other VMI present")


@pytest.fixture()
def vm0(node_maintenance_ns, unprivileged_client):
    name = f"vm-nodemaintenance-{random.randrange(99999)}"
    with VirtualMachineForTests(
        name=name,
        namespace=node_maintenance_ns.name,
        eviction=True,
        body=fedora_vm_body(name),
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.fixture()
def windows_initial_boot_time(vm_win10, winrmcli_pod):
    LOGGER.info(
        f"Windows VM {vm_win10.vmi.name} is booting up, it may take up to 10 mins."
    )
    boot_time = check_windows_boot_time(vm_win10, winrmcli_pod, timeout=600)
    yield boot_time


@pytest.fixture()
def winrmcli_pod(vm_win10, nodes):
    # For node maintenance tests winrmcli-pod and VMI should be located on different nodes
    node_for_winrmcli = list(
        filter(lambda n: n.name != vm_win10.vmi.virt_launcher_pod.node.name, nodes)
    )
    assert len(node_for_winrmcli) > 0, "No available nodes for winrmcli pod"

    with WinRMcliPod(
        name="winrmcli-pod",
        namespace=vm_win10.namespace,
        node_selector=node_for_winrmcli[0].name,
    ) as winrm_pod:
        winrm_pod.wait_for_status(status=winrm_pod.Status.RUNNING, timeout=60)
        yield winrm_pod


@pytest.fixture()
def vm_win10(dv_win10, node_maintenance_ns, unprivileged_client):
    vm_name = "windows-node-maintenance"
    with VirtualMachineForTestsFromTemplate(
        name=vm_name,
        namespace=node_maintenance_ns.name,
        client=unprivileged_client,
        labels=dv_win10.template_labels,
        template_dv=dv_win10.name,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.fixture()
def dv_win10(images_external_http_server, node_maintenance_ns):
    template_labels = [
        f"{Template.Labels.OS}/win10",
        f"{Template.Labels.WORKLOAD}/desktop",
        f"{Template.Labels.FLAVOR}/large",
    ]
    with DataVolumeTestResource(
        name="dv-windows-node-maintenance",
        namespace=node_maintenance_ns.name,
        url=f"{images_external_http_server}windows-images/window_qcow2_images/win_10.qcow2",
        size="30Gi",
        access_modes="ReadWriteMany",
        volume_mode="Block",
        template_labels=template_labels,
    ) as dv:
        dv.wait(timeout=1200)
        yield dv


def check_windows_boot_time(vm, winrmcli_pod, timeout=120):
    command = [
        "bash",
        "-c",
        f"/bin/winrm-cli -hostname {vm.vmi.virt_launcher_pod.instance.status.podIP} \
        -username Administrator -password Heslo123 \
        'wmic os get lastbootuptime'",
    ]
    pod_output_samples = TimeoutSampler(
        timeout=timeout, sleep=15, func=winrmcli_pod.execute, command=command
    )
    for pod_output in pod_output_samples:
        if "LastBootUpTime" in str(pod_output):
            return str(pod_output)


def check_draining_process(default_client, source_pod, vm):
    source_node = source_pod.node
    virt_utils.wait_for_node_unschedulable_status(node=source_node, status=True)
    for migration_job in VirtualMachineInstanceMigration.get(default_client):
        if migration_job.instance.spec.vmiName == vm.name:
            migration_job.wait_for_status(
                status=migration_job.Status.SUCCEEDED, timeout=600
            )

    source_pod.wait_deleted()
    target_node = vm.vmi.virt_launcher_pod.node
    assert target_node != source_node, "Source Node and Target Node should be different"


@pytest.mark.polarion("CNV-2286")
def test_node_maintenance_fedora(
    skip_when_other_vmi_present, skip_when_one_node, vm0, default_client
):
    source_pod = vm0.vmi.virt_launcher_pod
    source_node = source_pod.node

    with running_sleep_in_fedora(vm0):
        with NodeMaintenance(name="node-maintenance-job", node=source_node) as nm:
            nm.wait_for_status(status=nm.Status.RUNNING)
            check_draining_process(
                default_client=default_client, source_pod=source_pod, vm=vm0
            )
            nm.wait_for_status(status=nm.Status.SUCCEEDED)
        virt_utils.wait_for_node_unschedulable_status(node=source_node, status=False)


@pytest.mark.polarion("CNV-3006")
def test_node_drain_console(
    skip_when_other_vmi_present, skip_when_one_node, vm0, default_client
):
    source_pod = vm0.vmi.virt_launcher_pod
    source_node = source_pod.node

    with running_sleep_in_fedora(vm0):
        with drain_node_console(node=source_node):
            check_draining_process(
                default_client=default_client, source_pod=source_pod, vm=vm0
            )
        virt_utils.wait_for_node_unschedulable_status(node=source_node, status=False)


@pytest.mark.polarion("CNV-2048")
def test_node_maintenance_windows(
    skip_when_other_vmi_present,
    skip_when_one_node,
    vm_win10,
    winrmcli_pod,
    windows_initial_boot_time,
    default_client,
):
    source_pod = vm_win10.vmi.virt_launcher_pod
    source_node = source_pod.node

    with drain_node_console(node=source_node):
        check_draining_process(
            default_client=default_client, source_pod=source_pod, vm=vm_win10
        )
        boot_time_after_migration = check_windows_boot_time(vm_win10, winrmcli_pod)
        assert (
            boot_time_after_migration == windows_initial_boot_time
        ), f"Initial time: {windows_initial_boot_time}. Time after migration: {boot_time_after_migration}"

    virt_utils.wait_for_node_unschedulable_status(node=source_node, status=False)
