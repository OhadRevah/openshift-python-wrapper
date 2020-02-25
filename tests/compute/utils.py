# -*- coding: utf-8 -*-

import logging

import tests.network.utils as network_utils
from pytest_testconfig import config as py_config
from resources.pod import Pod
from rrmngmnt import ssh, user
from utilities import console
from utilities.virt import wait_for_vm_interfaces


LOGGER = logging.getLogger(__name__)


class WinRMcliPod(Pod):
    def __init__(self, name, namespace, node_selector=None):
        super().__init__(name=name, namespace=namespace)
        self.node_selector = node_selector

    def to_dict(self):
        res = super().to_dict()
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


def execute_winrm_cmd(
    vmi_ip, winrmcli_pod, cmd, timeout=20, target_vm=False, helper_vm=False,
):
    if helper_vm:
        LOGGER.info(f"Running {cmd} via helper VM.")
        return execute_winrm_in_vm(target_vm=target_vm, helper_vm=helper_vm, cmd=cmd)
    else:
        LOGGER.info(f"Running {cmd} via winrm pod.")

        winrmcli_cmd = [
            "bash",
            "-c",
            f"/bin/winrm-cli -hostname {vmi_ip} \
            -username {py_config['windows_username']} -password {py_config['windows_password']} \
            '{cmd}'",
        ]

        return winrmcli_pod.execute(winrmcli_cmd, timeout=timeout)


def execute_winrm_in_vm(target_vm, helper_vm, cmd):
    target_vm_ip = network_utils.get_vmi_ip_v4_by_name(
        vmi=target_vm.vmi, name=[*target_vm.networks][0]
    )

    cmd = (
        f"podman run -it docker.io/kubevirt/winrmcli winrm-cli -hostname "
        f"{target_vm_ip} -username {py_config['windows_username']} -password "
        f"{py_config['windows_password']} '{cmd}'"
    ).split(" ")

    ssh_user = user.User(
        name=console.Fedora.USERNAME, password=console.Fedora.PASSWORD,
    )

    return ssh.RemoteExecutor(
        user=ssh_user,
        address=str(
            network_utils.get_vmi_ip_v4_by_name(
                vmi=helper_vm.vmi, name=[*helper_vm.networks][0]
            )
        ),
    ).run_cmd(cmd=cmd, tcp_timeout=480, io_timeout=480)[1]


def nmcli_add_con_cmds(iface, ip, default_gw, dns_server):
    bootcmds = [f"nmcli con add type ethernet con-name {iface} ifname {iface}"]

    # On bare metal cluster, address is acquired by DHCP
    # Default GW is set to eth1, thus should be removed from eth0
    if py_config["bare_metal_cluster"]:
        bootcmds += [
            "nmcli connection modify eth1 ipv4.method auto",
            "route del default gw  0.0.0.0 eth0",
        ]
    else:
        bootcmds += [
            f"nmcli con mod {iface} ipv4.addresses {ip}/24 "
            f"ipv4.method manual connection.autoconnect-priority 1 ipv6.method ignore",
        ]
    bootcmds += [f"nmcli con up {iface}"]

    # On PSI, change default GW to brcnv network
    if not py_config["bare_metal_cluster"]:
        bootcmds += [
            f"ip route replace default via " f"{default_gw}",
            "route del default gw  0.0.0.0 eth0",
            f"bash -c 'echo \"nameserver " f'{dns_server}" ' f">/etc/resolv.conf'",
        ]

    return bootcmds
