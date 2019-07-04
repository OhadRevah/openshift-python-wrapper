# -*- coding: utf-8 -*-
"""
Network Migration test
"""

import logging

import pytest

from resources.namespace import Namespace
from resources.virtual_machine import VirtualMachineInstanceMigration
from tests.network.utils import bridge_nad, Bridge, VXLANTunnel, nmcli_add_con_cmds
from tests.utils import FedoraVirtualMachine, wait_for_vm_interfaces
from utilities import console

BR1TEST = "br1test"
VMAIP = "192.168.0.1"
VMBIP = "192.168.0.2"
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
                name="vxlan100",
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
def vma(namespace, network_utility_pods):
    networks = {BR1TEST: BR1TEST}
    bootcmds = []
    bootcmds.extend(nmcli_add_con_cmds("eth1", VMAIP))

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
def vmb(namespace, network_utility_pods):
    networks = {BR1TEST: BR1TEST}
    bootcmds = []
    bootcmds.extend(nmcli_add_con_cmds("eth1", VMBIP))

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
    wait_for_vm_interfaces(vmi=vmi, timeout=720)
    return vmi


@pytest.fixture(scope="module")
def running_vmib(vmb):
    vmi = vmb.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi, timeout=720)
    return vmi


def ping_in_backgroud(src_vm, dst_vm, dst_ip, namespace):
    """
    Start ping connectivity to the vm
    """

    LOGGER.info(f"Ping {dst_ip} from {src_vm} to {dst_vm}")
    with console.Fedora(vm=src_vm, namespace=namespace) as src_vm_console:
        src_vm_console.sendline(f"sudo ping -i 0.1 -c 2000 {dst_ip} > /tmp/ping.log &")
        src_vm_console.expect(
            "[1]", timeout=60
        )  # Verify the above cmd exectute successfully


def assert_low_packet_loss(ssh_vm, namespace):
    with console.Fedora(vm=ssh_vm, namespace=namespace) as ssh_vm_console:
        ssh_vm_console.sendline(f"sudo tail -f /tmp/ping.log | grep 'transmitted'")
        ssh_vm_console.expect("packet loss", timeout=300)
        ssh_vm_console.sendline(chr(3))  # Send ctrl+c to end tail cmd
        packet_loss = float(str(ssh_vm_console.before).split()[-2].strip("%"))
        LOGGER.info(f"Packet loss percentage {packet_loss}")
        assert packet_loss < 3.0


@pytest.mark.polarion("CNV-2060")
def test_ping_vm_migration(
    skip_if_no_multinode_cluster, namespace, vma, vmb, running_vmia, running_vmib
):

    ping_in_backgroud(
        running_vmia.name, running_vmib.name, dst_ip=VMBIP, namespace=namespace.name
    )

    src_node = running_vmib.instance.status.nodeName
    with VirtualMachineInstanceMigration(
        name="l2-migration", namespace=namespace.name, vmi=running_vmib
    ) as mig:

        mig.wait_for_status(status="Succeeded", timeout=720)
        assert running_vmib.instance.status.nodeName != src_node

    assert_low_packet_loss(running_vmia.name, namespace=namespace.name)
