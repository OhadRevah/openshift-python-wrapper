import logging

from pytest_testconfig import config as py_config
from resources.pod import Pod
from utilities.virt import wait_for_vm_interfaces


LOGGER = logging.getLogger(__name__)


class WinRMcliPod(Pod):
    def __init__(self, name, namespace, node_selector=None):
        super().__init__(name=name, namespace=namespace)
        self.node_selector = node_selector

    def _to_dict(self):
        res = super()._to_dict()
        res["spec"] = {
            "containers": [
                {
                    "name": "winrmcli-con",
                    "image": "kubevirt/winrmcli:latest",
                    "command": ["bash", "-c", "/usr/bin/sleep 6000"],
                }
            ]
        }
        if self.node_selector:
            res["spec"]["nodeSelector"] = {"kubernetes.io/hostname": self.node_selector}

        return res


def vm_started(vm, wait_for_interfaces=True):
    """ Start a VM and wait for its status to be 'Running'

    If wait_for_interfaces - wait for interfaces to be up.
    """

    vm.start(wait=True)
    vm.vmi.wait_until_running()
    if wait_for_interfaces:
        wait_for_vm_interfaces(vm.vmi)


def execute_winrm_cmd(vmi_ip, winrmcli_pod, cmd, timeout=20):

    LOGGER.info(f"Running {cmd} via winrm pod.")

    winrmcli_cmd = [
        "bash",
        "-c",
        f"/bin/winrm-cli -hostname {vmi_ip} \
        -username {py_config['windows_username']} -password {py_config['windows_password']} \
        '{cmd}'",
    ]

    return winrmcli_pod.execute(winrmcli_cmd, timeout=timeout)
