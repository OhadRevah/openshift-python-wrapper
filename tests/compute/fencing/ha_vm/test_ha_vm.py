# -*- coding: utf-8 -*-

"""
HA VM reboot and provisioning scenario tests.
"""

import logging

import pytest
from pytest_testconfig import config as py_config
from resources.machine import Machine
from resources.machine_health_check import MachineHealthCheck
from resources.utils import TimeoutSampler
from utilities import console
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    vm_console_run_commands,
)


pytestmark = pytest.mark.destructive

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def machine(ha_vm):
    return Machine(
        name=ha_vm.vmi.node.machine_name,
        namespace=py_config["machine_api_namespace"],
    )


@pytest.fixture()
def machine_health_check(machine):
    with MachineHealthCheck(
        name="ha-vm-mhc",
        namespace=py_config["machine_api_namespace"],
        cluster_name=machine.cluster_name,
        machineset_name=machine.machineset_name,
        unhealthy_timeout="60s",
        reboot_strategy=True,
    ) as mhc:
        yield mhc


@pytest.fixture()
def ha_vm(request, namespace, unprivileged_client):
    run_strategy = request.param["run_strategy"]
    name = f"ha-vm-test-{run_strategy}".lower()
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
        client=unprivileged_client,
        run_strategy=run_strategy,
    ) as vm:
        if run_strategy == "Manual":
            vm.start()
        vm.vmi.wait_until_running()
        yield vm


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
    "ha_vm",
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
def test_ha_vm_reboot(
    skip_if_workers_vms, machine_health_check, workers_ssh_executors, ha_vm
):
    orig_node = ha_vm.vmi.node
    stop_kubelet_on_node(
        node_ssh=workers_ssh_executors[ha_vm.vmi.node.name], node=orig_node
    )
    wait_and_verify_vmi_failover(vm=ha_vm)
    wait_node_restored(node=orig_node)
