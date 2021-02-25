"""
Test VM with memory requests/limits and guest memory for OOM.
"""

import logging
from contextlib import contextmanager
from multiprocessing import Process

import pytest
from resources.utils import TimeoutExpiredError, TimeoutSampler

from utilities import console
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    run_command,
    vm_console_run_commands,
    wait_for_console,
)


pytestmark = pytest.mark.tier3

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def oom_vm(namespace, unprivileged_client, rhel7_workers):
    name = "oom-vm"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
        client=unprivileged_client,
        running=True,
        ssh=True,
        cpu_cores=2,
        cpu_requests="2",
        cpu_limits="2",
        username=console.Fedora.USERNAME,
        password=console.Fedora.PASSWORD,
        rhel7_workers=rhel7_workers,
    ) as vm:
        vm.vmi.wait_until_running()
        wait_for_console(vm=vm, console_impl=console.Fedora)
        yield vm


def start_vm_stress(vm, console_impl):
    commands = [
        "nohup stress-ng --vm 1 --vm-bytes 100% --vm-method all --verify -t 15m -v --hdd 1 --io 1 &",
    ]
    vm_console_run_commands(console_impl=console_impl, vm=vm, commands=commands)


@contextmanager
def start_file_transfer(vm_ssh):
    file_name = "oom-test.txt"

    def _transfer_loop():
        while True:
            vm_ssh.fs.put(path_src=file_name, path_dst=file_name)

    run_command(
        command=["dd", "if=/dev/zero", f"of={file_name}", "bs=100M", "count=1"],
        verify_stderr=False,
    )

    transfer = Process(target=_transfer_loop)
    transfer.start()

    try:
        yield
    finally:
        transfer.terminate()
        run_command(command=["rm", "-f", file_name])


def wait_vm_oom(vm):
    LOGGER.info(f"Monitoring VM {vm.name} under stress for 15 min")
    virt_launcher_pod = vm.vmi.virt_launcher_pod
    samples = TimeoutSampler(
        wait_timeout=900, sleep=1, func=lambda: virt_launcher_pod.status
    )
    try:
        for sample in samples:
            if sample == virt_launcher_pod.Status.FAILED:
                return
    except TimeoutExpiredError:
        return True


@pytest.mark.polarion("CNV-5321")
def test_vm_oom(oom_vm):
    start_vm_stress(vm=oom_vm, console_impl=console.Fedora)
    with start_file_transfer(vm_ssh=oom_vm.ssh_exec):
        assert wait_vm_oom(vm=oom_vm), "VM crashed"
