import shlex

from utilities.constants import OS_FLAVOR_WINDOWS
from utilities.infra import run_ssh_commands
from utilities.virt import wait_for_ssh_connectivity


def verify_gpu_device_exists(vm):
    if vm.os_flavor.startswith(OS_FLAVOR_WINDOWS):
        assert "NVIDIA Tesla" in run_ssh_commands(
            host=vm.ssh_exec,
            commands=[shlex.split("wmic path win32_VideoController get name")],
        )[0]
    else:
        assert (
            run_ssh_commands(
                host=vm.ssh_exec,
                commands=[
                    "bash",
                    "-c",
                    "/sbin/lspci -nnk | grep NVIDIA | grep Tesla | wc -l",
                ],
            )[0].strip()
            == "1"
        )


def restart_and_check_device_exists(vm):
    vm.restart(wait=True)
    wait_for_ssh_connectivity(vm=vm)
    verify_gpu_device_exists(vm=vm)
