"""
Create Linux BOND.
Start a VM with bridge on Linux BOND.
"""
import shlex
from collections import OrderedDict

import pytest
import tests.network.utils as network_utils
from utilities.network import (
    BondNodeNetworkConfigurationPolicy,
    get_hosts_common_ports,
    network_nad,
)
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


@pytest.fixture(scope="class")
def bond_nad(bridge_device_matrix__class__, namespace):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="bond-nad",
        interface_name="brbond",
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def bond(
    link_aggregation_mode_no_connectivity_matrix__class__,
    network_utility_pods,
    nodes_active_nics,
    worker_node1,
):
    """
    Create BOND if setup support BOND
    """
    with BondNodeNetworkConfigurationPolicy(
        name="bondnncp",
        bond_name="test-bond",
        slaves=get_hosts_common_ports(nodes_active_nics=nodes_active_nics)[1:3],
        worker_pods=network_utility_pods,
        mode=link_aggregation_mode_no_connectivity_matrix__class__,
        mtu=1450,
        node_selector=worker_node1.name,
    ) as bond:
        yield bond


@pytest.fixture(scope="class")
def bond_bridge(
    bridge_device_matrix__class__, network_utility_pods, worker_node1, bond_nad, bond,
):
    """
    Create bridge and attach the BOND to it
    """
    with network_utils.network_device(
        interface_type=bridge_device_matrix__class__,
        nncp_name="bridge-on-bond",
        interface_name=bond_nad.bridge_name,
        network_utility_pods=network_utility_pods,
        ports=[bond.bond_name],
        node_selector=worker_node1.name,
    ) as br:
        yield br


@pytest.fixture(scope="class")
def bond_vm(
    worker_node1, namespace, unprivileged_client, bond_nad, bond_bridge,
):
    name = "bond-vm"
    networks = OrderedDict()
    networks[bond_nad.name] = bond_nad.name

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=worker_node1.name,
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
        client=unprivileged_client,
    ) as vm:
        yield vm


@pytest.mark.usefixtures("skip_no_bond_support")
class TestBondModes:
    @pytest.mark.polarion("CNV-4382")
    def test_bond_created(self, workers_ssh_executors, bond):
        bonding_path = "/sys/class/net/test-bond/bonding"
        _exec = workers_ssh_executors[bond.node_selector]
        mode = _exec.run_command(command=shlex.split(f"cat {bonding_path}/mode"))[1]
        slaves = _exec.run_command(command=shlex.split(f"cat {bonding_path}/slaves"))[1]
        worker_slaves = slaves.split()
        worker_slaves.sort()
        assert mode.split()[0] == bond.mode
        assert worker_slaves == bond.slaves

    @pytest.mark.polarion("CNV-4383")
    def test_vm_started(self, bond_vm):
        bond_vm.start(wait=True)
        bond_vm.vmi.wait_until_running()
        wait_for_vm_interfaces(vmi=bond_vm.vmi)
