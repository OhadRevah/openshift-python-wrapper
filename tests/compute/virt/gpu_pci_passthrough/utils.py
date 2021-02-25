import shlex

from ocp_resources.resource import ResourceEditor

from utilities.constants import GPU_DEVICE_NAME
from utilities.infra import run_ssh_commands
from utilities.virt import wait_for_ssh_connectivity


def update_vm_to_gpus_spec(vm):
    vm_dict = vm.instance.to_dict()
    vm_spec_dict = vm_dict["spec"]["template"]["spec"]
    vm_spec_dict["domain"]["devices"].pop("hostDevices", "No key Found")
    ResourceEditor(patches={vm: vm_dict}, action="replace").update()
    ResourceEditor(
        patches={
            vm: {
                "spec": {
                    "template": {
                        "spec": {
                            "domain": {
                                "devices": {
                                    "gpus": [
                                        {
                                            "deviceName": GPU_DEVICE_NAME,
                                            "name": "gpus",
                                        }
                                    ]
                                }
                            }
                        }
                    }
                }
            }
        }
    ).update()


def verify_gpu_device_exists(vm):
    if vm.os_flavor.startswith("win"):
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
