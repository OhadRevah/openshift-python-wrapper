# -*- coding: utf-8 -*-

import logging
import shlex

import pytest
from pytest_testconfig import config as py_config

from utilities import console
from utilities.constants import TIMEOUT_60MIN
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    enable_ssh_service_in_vm,
    migrate_and_verify,
    wait_for_vm_interfaces,
)


LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def vm_with_mem_load(
    unprivileged_client,
    nodes_common_cpu_model,
    namespace,
    data_volume_scope_function,
):
    with VirtualMachineForTests(
        name="vm-with-mem-load",
        namespace=namespace.name,
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
        client=unprivileged_client,
        running=True,
        ssh=True,
        cpu_cores=2,
        cpu_requests="2",
        cpu_limits="2",
        memory_requests="4196Mi",
        data_volume=data_volume_scope_function,
        username=console.Fedora.USERNAME,
        password=console.Fedora.PASSWORD,
    ) as vm:
        vm.vmi.wait_until_running()
        wait_for_vm_interfaces(vmi=vm.vmi)
        enable_ssh_service_in_vm(vm=vm, console_impl=console.Fedora)
        yield vm


@pytest.fixture()
def start_vm_stress(vm_with_mem_load):
    # TODO: Increase the load with F33 (since F32 is bit flaky)
    LOGGER.info("Running memory load in VM")
    command = (
        "nohup sudo stress-ng --vm 1 --vm-bytes 15% --vm-method all --verify -t 15m -v --hdd 1 --io 1 "
        "&> /tmp/OUT1 & echo $!"
    )
    vm_with_mem_load.ssh_exec.run_command(command=shlex.split(command))


@pytest.fixture()
def vm_info_before_migrate(vm_with_mem_load):
    source_node = vm_with_mem_load.vmi.virt_launcher_pod.node
    stress_ng_pid_before = get_stress_ng_pid(ssh_exec=vm_with_mem_load.ssh_exec)
    return source_node, stress_ng_pid_before


@pytest.fixture()
def migrate_vm_with_memory_load(vm_info_before_migrate, vm_with_mem_load):
    migrate_and_verify(vm=vm_with_mem_load, timeout=TIMEOUT_60MIN)
    assert (
        vm_info_before_migrate[0] != vm_with_mem_load.vmi.virt_launcher_pod.node
    ), "migration completed but vm on source node"


def get_stress_ng_pid(ssh_exec):
    LOGGER.info("Get pid of stress-ng")
    return ssh_exec.run_command(
        command=shlex.split("pgrep stress-ng"), tcp_timeout=60, io_timeout=60
    )[1]


@pytest.mark.parametrize(
    "data_volume_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-fedora-mem-load-vm",
                "image": py_config["latest_fedora_version"]["image_path"],
                "storage_class": py_config["default_storage_class"],
                "dv_size": py_config["latest_fedora_version"]["dv_size"],
            },
            marks=pytest.mark.polarion("CNV-4661"),
            id="case: migrate vm with memory load on the guest",
        ),
    ],
    indirect=True,
)
def test_vm_migarte_with_memory_load(
    data_volume_scope_function,
    vm_with_mem_load,
    start_vm_stress,
    vm_info_before_migrate,
    migrate_vm_with_memory_load,
):
    _, stress_ng_pid_before = vm_info_before_migrate
    stress_ng_pid_after = get_stress_ng_pid(ssh_exec=vm_with_mem_load.ssh_exec)
    assert (
        stress_ng_pid_before == stress_ng_pid_after
    ), "stress ng stopped or changed during migration"
