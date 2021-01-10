# -*- coding: utf-8 -*-

"""
HA VM reboot and provisioning scenario tests.
"""

import logging

import pytest
from pytest_testconfig import config as py_config
from resources.machine import Machine
from resources.machine_health_check import MachineHealthCheck
from resources.template import Template
from resources.utils import TimeoutSampler

from utilities import console
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    VirtualMachineForTestsFromTemplate,
    fedora_vm_body,
    vm_console_run_commands,
    wait_for_console,
)


pytestmark = pytest.mark.destructive

LOGGER = logging.getLogger(__name__)
DV_DICT = {
    "dv_name": py_config["latest_fedora_version"]["template_labels"]["os"],
    "image": py_config["latest_fedora_version"]["image_path"],
    "dv_size": py_config["latest_fedora_version"]["dv_size"],
    "storage_class": "nfs",
    "access_modes": "ReadWriteMany",
    "volume_mode": "Filesystem",
}


@pytest.fixture(scope="module")
def machine(worker_node1):
    return Machine(
        name=worker_node1.machine_name,
        namespace=py_config["machine_api_namespace"],
    )


@pytest.fixture()
def machine_health_check_reboot(machine):
    with MachineHealthCheck(
        name="ha-vm-mhc",
        namespace=machine.namespace,
        cluster_name=machine.cluster_name,
        machineset_name=machine.machineset_name,
        unhealthy_timeout="60s",
        reboot_strategy=True,
    ) as mhc:
        yield mhc


@pytest.fixture()
def ha_vm_container_disk(request, unprivileged_client, namespace):
    run_strategy = request.param["run_strategy"]
    name = f"ha-vm-container-disk-{run_strategy}".lower()
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
        client=unprivileged_client,
        run_strategy=run_strategy,
    ) as vm:
        vm_ready_for_test(vm=vm)
        yield vm


@pytest.fixture()
def ha_vm_dv_disk(
    request, unprivileged_client, namespace, golden_image_data_volume_scope_function
):
    run_strategy = request.param["run_strategy"]
    name = f"ha-vm-dv-disk-{run_strategy}".lower()
    with VirtualMachineForTestsFromTemplate(
        name=name,
        namespace=namespace.name,
        client=unprivileged_client,
        labels=Template.generate_template_labels(
            **py_config["latest_fedora_version"]["template_labels"]
        ),
        data_volume=golden_image_data_volume_scope_function,
        run_strategy=run_strategy,
    ) as vm:
        vm_ready_for_test(vm=vm)
        yield vm


def vm_ready_for_test(vm):
    if vm.run_strategy == "Manual":
        vm.start()
    vm.vmi.wait_until_running()
    wait_for_console(
        vm=vm,
        console_impl=console.Fedora,
    )


def stop_kubelet_on_node(node_ssh, node):
    LOGGER.info(f"Stopping kubelet on node {node.name}")
    node_ssh.run_command(command=["sudo", "systemctl", "stop", "kubelet.service"])
    wait_node_status(node=node_ssh, status=False)


def wait_and_verify_vmi_failover(vm):
    LOGGER.info(f"Waiting VMI {vm.vmi.name} failover to new node")
    old_uid = vm.vmi.instance.metadata.uid
    old_node = vm.vmi.node

    if vm.instance.spec.runStrategy == "Manual":
        vm.vmi.wait_for_status(status="Failed")
        vm.start()
    else:
        vm.vmi.wait_for_status(status="Scheduling")
    vm.vmi.wait_until_running()
    wait_for_console(
        vm=vm,
        console_impl=console.Fedora,
    )

    new_uid = vm.vmi.instance.metadata.uid
    new_node = vm.vmi.node

    assert old_uid != new_uid, "Old VMI still exists"
    assert old_node.name != new_node.name, "VMI still on old node"

    vm_console_run_commands(
        console_impl=console.Fedora,
        vm=vm,
        commands=["cat /etc/os-release"],
    )


def wait_node_restored(node):
    LOGGER.info(f"Waiting node {node.name} to be added to cluster and Ready")
    node.wait(timeout=1200)
    wait_node_status(node=node)


def wait_node_status(node, status=True):
    """Wait for node status Ready (status=True) or NotReady (status=False)"""
    for sample in TimeoutSampler(timeout=60, sleep=1, func=lambda: node.kubelet_ready):
        if (status and sample) or (not status and not sample):
            return


@pytest.mark.parametrize(
    "ha_vm_container_disk",
    [
        pytest.param(
            {"run_strategy": "Always"},
            marks=pytest.mark.polarion("CNV-4152"),
            id="case: Always",
        ),
        pytest.param(
            {"run_strategy": "RerunOnFailure"},
            marks=pytest.mark.polarion("CNV-4154"),
            id="case: RerunOnFailure",
        ),
        pytest.param(
            {"run_strategy": "Manual"},
            marks=pytest.mark.polarion("CNV-4155"),
            id="case: Manual",
        ),
    ],
    indirect=True,
)
def test_ha_vm_container_disk_reboot(
    skip_if_workers_vms,
    workers_ssh_executors,
    machine_health_check_reboot,
    ha_vm_container_disk,
):
    orig_node = ha_vm_container_disk.vmi.node
    stop_kubelet_on_node(
        node_ssh=workers_ssh_executors[ha_vm_container_disk.vmi.node.name],
        node=orig_node,
    )
    wait_and_verify_vmi_failover(vm=ha_vm_container_disk)
    wait_node_restored(node=orig_node)


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_function, ha_vm_dv_disk",
    [
        pytest.param(
            DV_DICT,
            {"run_strategy": "Always"},
            marks=pytest.mark.polarion("CNV-5212"),
            id="case: Always",
        ),
        pytest.param(
            DV_DICT,
            {"run_strategy": "RerunOnFailure"},
            marks=pytest.mark.polarion("CNV-5213"),
            id="case: RerunOnFailure",
        ),
        pytest.param(
            DV_DICT,
            {"run_strategy": "Manual"},
            marks=pytest.mark.polarion("CNV-5214"),
            id="case: Manual",
        ),
    ],
    indirect=True,
)
def test_ha_vm_dv_disk_reboot(
    skip_if_workers_vms,
    workers_ssh_executors,
    machine_health_check_reboot,
    ha_vm_dv_disk,
):
    orig_node = ha_vm_dv_disk.vmi.node
    vm_console_run_commands(
        console_impl=console.Fedora,
        vm=ha_vm_dv_disk,
        commands=["echo test >> ha-test"],
    )
    stop_kubelet_on_node(
        node_ssh=workers_ssh_executors[ha_vm_container_disk.vmi.node.name],
        node=orig_node,
    )
    wait_and_verify_vmi_failover(vm=ha_vm_container_disk)
    wait_node_restored(node=orig_node)
    vm_console_run_commands(
        console_impl=console.Fedora,
        vm=ha_vm_dv_disk,
        commands=["cat ha-test"],
    )
