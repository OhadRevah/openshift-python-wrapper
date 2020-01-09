"""
 Draining node by Node Maintenance Operator
"""

import logging
import random
from contextlib import contextmanager
from subprocess import run

import pytest
from pytest_lazyfixture import lazy_fixture
from pytest_testconfig import config as py_config
from resources.datavolume import DataVolume
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
from utilities.infra import Images, create_ns
from utilities.storage import create_dv
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    VirtualMachineForTestsFromTemplate,
    fedora_vm_body,
)


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module", autouse=True)
def node_maintenance_ns(unprivileged_client):
    yield from create_ns(client=unprivileged_client, name="node-maintenance-ns")


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
def vm_container_disk_fedora(node_maintenance_ns, unprivileged_client):
    name = f"vm-nodemaintenance-{random.randrange(99999)}"
    with VirtualMachineForTests(
        name=name,
        namespace=node_maintenance_ns.name,
        eviction=True,
        body=fedora_vm_body(name),
        client=unprivileged_client,
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.fixture()
def vm_template_dv_rhel8(
    node_maintenance_ns, unprivileged_client, images_external_http_server,
):
    vm_dv_name = "rhel8-template-node-maintenance"
    url = f"{images_external_http_server}{Images.Rhel.DIR}/{Images.Rhel.RHEL8_0_IMG}"
    template_labels_dict = {
        "os": "rhel8.0",
        "workload": "server",
        "flavor": "tiny",
    }
    with create_dv(
        source="http",
        dv_name=vm_dv_name,
        namespace=node_maintenance_ns.name,
        url=url,
        size="30Gi",
        content_type=DataVolume.ContentType.KUBEVIRT,
        access_modes=DataVolume.AccessMode.RWX,
        volume_mode=DataVolume.VolumeMode.BLOCK,
        storage_class=py_config["default_storage_class"],
    ) as dv:
        dv.wait(timeout=1200)
        with VirtualMachineForTestsFromTemplate(
            name="dv-rhel8-node-maintenance",
            namespace=node_maintenance_ns.name,
            client=unprivileged_client,
            labels=Template.generate_template_labels(**template_labels_dict),
            template_dv=dv.name,
        ) as vm:
            vm.start(wait=True)
            vm.vmi.wait_until_running()
            yield vm


@pytest.fixture()
def windows_initial_boot_time(vm_win10, winrmcli_pod):
    LOGGER.info(
        f"Windows VM {vm_win10.vmi.name} is booting up, it may take up to 20 minutess."
    )
    boot_time = check_windows_boot_time(vm_win10, winrmcli_pod)
    yield boot_time


@pytest.fixture()
def winrmcli_pod(vm_win10, schedulable_nodes):
    # For node maintenance tests winrmcli-pod and VMI should be located on different nodes
    node_for_winrmcli = list(
        filter(
            lambda n: n.name != vm_win10.vmi.virt_launcher_pod.node.name,
            schedulable_nodes,
        )
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
def vm_win10(node_maintenance_ns, unprivileged_client, images_external_http_server):
    vm_dv_name = "windows-template-node-maintenance"
    url = (
        f"{images_external_http_server}{Images.Windows.DIR}/{Images.Windows.WIM10_IMG}"
    )
    template_labels_dict = {
        "os": "win10",
        "workload": "desktop",
        "flavor": "medium",
    }
    with create_dv(
        source="http",
        dv_name=vm_dv_name,
        namespace=node_maintenance_ns.name,
        url=url,
        size="30Gi",
        content_type=DataVolume.ContentType.KUBEVIRT,
        access_modes=DataVolume.AccessMode.RWX,
        volume_mode=DataVolume.VolumeMode.BLOCK,
        storage_class=py_config["default_storage_class"],
    ) as dv:
        dv.wait(timeout=1200)
        with VirtualMachineForTestsFromTemplate(
            name=vm_dv_name,
            namespace=node_maintenance_ns.name,
            client=unprivileged_client,
            labels=Template.generate_template_labels(**template_labels_dict),
            template_dv=dv.name,
        ) as vm:
            vm.start(wait=True)
            vm.vmi.wait_until_running()
            yield vm


def check_windows_boot_time(vm, winrmcli_pod, timeout=1200):
    command = [
        "bash",
        "-c",
        f"/bin/winrm-cli -hostname {vm.vmi.virt_launcher_pod.instance.status.podIP} \
        -username {py_config['windows_username']} -password {py_config['windows_password']} \
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
def test_node_maintenance_job(
    skip_when_other_vmi_present,
    skip_when_one_node,
    vm_container_disk_fedora,
    default_client,
):
    source_pod = vm_container_disk_fedora.vmi.virt_launcher_pod
    source_node = source_pod.node

    with running_sleep_in_linux(console.Fedora(vm_container_disk_fedora)):
        with NodeMaintenance(name="node-maintenance-job", node=source_node) as nm:
            nm.wait_for_status(status=nm.Status.RUNNING)
            check_draining_process(
                default_client=default_client,
                source_pod=source_pod,
                vm=vm_container_disk_fedora,
            )
            nm.wait_for_status(status=nm.Status.SUCCEEDED)
        virt_utils.wait_for_node_unschedulable_status(node=source_node, status=False)


@pytest.mark.parametrize(
    "vm, os",
    [
        pytest.param(
            lazy_fixture("vm_container_disk_fedora"),
            "Fedora",
            marks=(pytest.mark.polarion("CNV-3006")),
        ),
        pytest.param(
            lazy_fixture("vm_template_dv_rhel8"),
            "RHEL",
            marks=(pytest.mark.polarion("CNV-2292")),
        ),
    ],
)
def test_node_drain_using_console(
    skip_when_other_vmi_present, skip_when_one_node, default_client, vm, os
):
    source_pod = vm.vmi.virt_launcher_pod
    source_node = source_pod.node

    vm_cli = console.Fedora(vm) if os == "Fedora" else console.RHEL(vm)

    with running_sleep_in_linux(vm_cli):
        with drain_node_console(node=source_node):
            check_draining_process(
                default_client=default_client, source_pod=source_pod, vm=vm
            )
        virt_utils.wait_for_node_unschedulable_status(node=source_node, status=False)


@pytest.mark.polarion("CNV-2048")
def test_node_drain_template_windows(
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
