# -*- coding: utf-8 -*-
import logging

from resources.pod import Pod
from utilities.infra import ClusterHosts
from utilities.virt import wait_for_vm_interfaces


LOGGER = logging.getLogger(__name__)


class WinRMcliPod(Pod):
    def __init__(self, name, namespace, node_selector=None, teardown=True):
        super().__init__(name=name, namespace=namespace, teardown=teardown)
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


def nmcli_add_con_cmds(workers_type, iface, ip, default_gw, dns_server):
    bootcmds = [f"nmcli con add type ethernet con-name {iface} ifname {iface}"]

    # On bare metal cluster, address is acquired by DHCP
    # Default GW is set to eth1, thus should be removed from eth0
    if workers_type == ClusterHosts.Type.PHYSICAL:
        bootcmds += [
            "nmcli connection modify eth1 ipv4.method auto",
            "route del default gw  0.0.0.0 eth0",
        ]
    else:
        bootcmds += [
            f"nmcli con mod {iface} ipv4.addresses {ip}/24 "
            f"ipv4.method manual connection.autoconnect-priority 1 ipv6.method ignore"
        ]
    bootcmds += [f"nmcli con up {iface}"]

    # On PSI, change default GW to brcnv network
    if workers_type == ClusterHosts.Type.VIRTUAL:
        bootcmds += [
            f"ip route replace default via " f"{default_gw}",
            "route del default gw  0.0.0.0 eth0",
            f"bash -c 'echo \"nameserver " f'{dns_server}" ' f">/etc/resolv.conf'",
        ]

    return bootcmds
