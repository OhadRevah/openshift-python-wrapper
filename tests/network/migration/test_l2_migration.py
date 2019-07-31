# -*- coding: utf-8 -*-
"""
Network Migration test
"""

import logging

import pytest

from resources.namespace import Namespace
from resources.virtual_machine import VirtualMachineInstanceMigration
from tests.network.utils import (
    bridge_nad,
    Bridge,
    VXLANTunnel,
    nmcli_add_con_cmds,
    get_vmi_ip_v4_by_name,
)
from tests.utils import FedoraVirtualMachine, wait_for_vm_interfaces
from utilities import console

BR1TEST = "br1test"
LOGGER = logging.getLogger(__name__)


class BridgedFedoraVirtualMachine(FedoraVirtualMachine):
    def __init__(
        self,
        name,
        namespace,
        client=None,
        interfaces=None,
        networks=None,
        node_selector=None,
        bootcmds=None,
    ):
        super().__init__(
            name=name,
            namespace=namespace,
            client=client,
            interfaces=interfaces,
            networks=networks,
            node_selector=node_selector,
        )
        self.bootcmds = bootcmds

    def _cloud_init_user_data(self):
        data = super()._cloud_init_user_data()
        data["bootcmd"] = self.bootcmds
        return data


@pytest.fixture(scope="module", autouse=True)
def namespace():
    with Namespace(name="network-migration-test") as ns:
        yield ns


@pytest.fixture(scope="module", autouse=True)
def bridge_on_all_nodes(network_utility_pods, nodes_active_nics, multi_nics_nodes):
    master_index = 1 if multi_nics_nodes else None
    with Bridge(
        name=BR1TEST,
        worker_pods=network_utility_pods,
        master_index=master_index,
        nodes_nics=nodes_active_nics,
    ) as br:
        if not multi_nics_nodes:
            with VXLANTunnel(
                name="vxlan_mig_10",
                worker_pods=network_utility_pods,
                vxlan_id=10,
                master_bridge=br.name,
                nodes_nics=nodes_active_nics,
            ):
                yield br
        else:
            yield br


@pytest.fixture(scope="module", autouse=True)
def br1test_nad(namespace):
    with bridge_nad(namespace=namespace, name=BR1TEST, bridge=BR1TEST) as nad:
        yield nad


@pytest.fixture(scope="module")
def vma(namespace):
    networks = {BR1TEST: BR1TEST}
    bootcmds = []
    bootcmds.extend(nmcli_add_con_cmds("eth1", "192.168.0.1"))

    with BridgedFedoraVirtualMachine(
        namespace=namespace.name,
        name="vma",
        networks=networks,
        interfaces=sorted(networks.keys()),
        bootcmds=bootcmds,
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture(scope="module")
def vmb(namespace):
    networks = {BR1TEST: BR1TEST}
    bootcmds = []
    bootcmds.extend(nmcli_add_con_cmds("eth1", "192.168.0.2"))

    with BridgedFedoraVirtualMachine(
        namespace=namespace.name,
        name="vmb",
        networks=networks,
        interfaces=sorted(networks.keys()),
        bootcmds=bootcmds,
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture(scope="module")
def running_vmia(vma):
    vmi = vma.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    yield vmi


@pytest.fixture(scope="module")
def running_vmib(vmb):
    vmi = vmb.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    yield vmi


def ping_in_backgroud(vm, dst_vm):
    dst_ip = get_vmi_ip_v4_by_name(dst_vm.vmi, BR1TEST)
    LOGGER.info(f"Ping {dst_ip} from {vm.name} to {dst_vm.name}")
    with console.Fedora(vm=vm) as vmc:
        vmc.sendline(f"sudo ping -i 0.1 {dst_ip} > /tmp/ping.log &")
        vmc.expect(r"\[\d+\].*\d+", timeout=10)
        vmc.sendline("echo $! > /tmp/ping.pid")


def assert_low_packet_loss(vm):
    with console.Fedora(vm=vm) as vmc:
        vmc.sendline(f"sudo kill -SIGINT `cat /tmp/ping.pid`")
        vmc.sendline(f"grep 'transmitted' /tmp/ping.log")
        vmc.expect("packet loss", 10)
        packet_loss = float(str(vmc.before).split()[-2].strip("%"))
        LOGGER.info(f"Packet loss percentage {packet_loss}")
        assert packet_loss < 3.0


@pytest.mark.polarion("CNV-2060")
def test_ping_vm_migration(skip_when_one_node, vma, vmb, running_vmia, running_vmib):
    ping_in_backgroud(vma, vmb)
    src_node = running_vmib.instance.status.nodeName
    with VirtualMachineInstanceMigration(
        name="l2-migration", namespace=running_vmib.namespace, vmi=running_vmib
    ) as mig:
        mig.wait_for_status(status="Succeeded", timeout=720)
        assert running_vmib.instance.status.nodeName != src_node

    assert_low_packet_loss(vma)
