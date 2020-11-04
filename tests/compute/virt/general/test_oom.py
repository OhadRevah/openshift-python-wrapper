"""
Test VM with memory requests/limits and guest memory for OOM.
"""

import logging
from contextlib import contextmanager
from multiprocessing import Process

import pytest
from resources.utils import TimeoutExpiredError, TimeoutSampler
from tests.compute.utils import rrmngmnt_host
from utilities import console
from utilities.infra import BUG_STATUS_CLOSED
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
def oom_vm(request, namespace, unprivileged_client):
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
        memory_requests=request.param["requests"],
        memory_limits=request.param["limits"],
        memory_guest=request.param["guest"],
    ) as vm:
        vm.vmi.wait_until_running()
        wait_for_console(vm=vm, console_impl=console.Fedora)
        yield vm


@pytest.fixture()
def vm_ssh_executor(oom_vm):
    return rrmngmnt_host(
        usr=console.Fedora.USERNAME,
        passwd=console.Fedora.PASSWORD,
        ip=oom_vm.ssh_service.service_ip,
        port=oom_vm.ssh_service.service_port,
    )


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
        timeout=900, sleep=1, func=lambda: virt_launcher_pod.status
    )
    try:
        for sample in samples:
            if sample == virt_launcher_pod.Status.FAILED:
                return
    except TimeoutExpiredError:
        return True


@pytest.mark.parametrize(
    "oom_vm",
    [
        pytest.param(
            {"requests": "8192Mi", "limits": "8192Mi", "guest": "8192Mi"},
            marks=(
                pytest.mark.polarion("CNV-4482"),
                pytest.mark.bugzilla(
                    1885418, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
            ),
            id="case: guest memory == memory requests & limits",
        ),
        pytest.param(
            {"requests": "8292Mi", "limits": "8292Mi", "guest": "8192Mi"},
            marks=pytest.mark.polarion("CNV-5321"),
            id="case: memory requests & limits > guest memory",
        ),
    ],
    indirect=True,
)
def test_vm_oom(oom_vm, vm_ssh_executor):
    start_vm_stress(vm=oom_vm, console_impl=console.Fedora)
    with start_file_transfer(vm_ssh=vm_ssh_executor):
        assert wait_vm_oom(vm=oom_vm), "VM crashed"
