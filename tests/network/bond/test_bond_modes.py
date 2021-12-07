"""
Create Linux BOND.
Start a VM with bridge on Linux BOND.
"""
from collections import OrderedDict
from contextlib import contextmanager

import pytest

import utilities.network
from utilities.infra import ExecCommandOnPod
from utilities.network import BondNodeNetworkConfigurationPolicy, network_nad
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


pytestmark = pytest.mark.sno


class BondNodeNetworkConfigurationPolicyWithSlaves(BondNodeNetworkConfigurationPolicy):
    def to_dict(self):
        res = super().to_dict()
        self.iface["link-aggregation"]["slaves"] = self.iface["link-aggregation"].pop(
            "port"
        )
        return res


def assert_bond_validation(utility_pods, bond):
    pod_exec = ExecCommandOnPod(utility_pods=utility_pods, node=bond.node_selector)
    bonding_path = f"/sys/class/net/{bond.bond_name}/bonding"
    mode = pod_exec.exec(command=f"cat {bonding_path}/mode")
    # TODO: rename 'slaves' once file is renamed (offensive language)
    bond_ports = pod_exec.exec(command=f"cat {bonding_path}/slaves")
    worker_bond_ports = bond_ports.split()
    worker_bond_ports.sort()
    bond.bond_ports.sort()
    assert mode.split()[0] == bond.mode
    assert worker_bond_ports == bond.bond_ports


@contextmanager
def create_bond(bond_idx, bond_ports, worker_pods, mode, node_selector, options=None):
    with BondNodeNetworkConfigurationPolicy(
        name=f"bond{bond_idx}nncp",
        bond_name=f"bond{bond_idx}",
        bond_ports=bond_ports,
        worker_pods=worker_pods,
        mode=mode,
        mtu=1450,
        node_selector=node_selector,
        options=options,
    ) as bond:
        yield bond


@contextmanager
def create_vm(namespace, nad, node_selector, unprivileged_client):
    name = "bond-vm"
    networks = OrderedDict()
    networks[nad.name] = nad.name

    with VirtualMachineForTests(
        namespace=namespace,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=node_selector,
        client=unprivileged_client,
        ssh=False,
    ) as vm:
        yield vm


@contextmanager
def bridge_on_bond(
    interface_type,
    utility_pods,
    node_selector,
    interface_name,
    ports,
):
    """
    Create bridge and attach the BOND to it
    """
    with utilities.network.network_device(
        interface_type=interface_type,
        nncp_name="bridge-on-bond",
        interface_name=interface_name,
        network_utility_pods=utility_pods,
        ports=ports,
        node_selector=node_selector,
    ) as br:
        yield br


@pytest.fixture(scope="class")
def bond_modes_nad(bridge_device_matrix__class__, namespace):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="bond-nad",
        interface_name="brbond",
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def matrix_bond_modes_bond(
    index_number,
    link_aggregation_mode_no_connectivity_matrix__class__,
    utility_pods,
    nodes_available_nics,
    worker_node1,
):
    """
    Create BOND if setup support BOND
    """
    with create_bond(
        bond_idx=next(index_number),
        bond_ports=nodes_available_nics[worker_node1.name][-2:],
        worker_pods=utility_pods,
        mode=link_aggregation_mode_no_connectivity_matrix__class__,
        node_selector=worker_node1.name,
    ) as bond:
        yield bond


@pytest.fixture(scope="class")
def matrix_bond_modes_bridge(
    bridge_device_matrix__class__,
    utility_pods,
    worker_node1,
    bond_modes_nad,
    matrix_bond_modes_bond,
):
    """
    Create bridge and attach the BOND to it
    """
    with bridge_on_bond(
        interface_type=bridge_device_matrix__class__,
        utility_pods=utility_pods,
        node_selector=worker_node1.name,
        interface_name=bond_modes_nad.bridge_name,
        ports=[matrix_bond_modes_bond.bond_name],
    ) as br:
        yield br


@pytest.fixture(scope="class")
def bond_modes_vm(
    worker_node1,
    namespace,
    unprivileged_client,
    bond_modes_nad,
    matrix_bond_modes_bridge,
):
    with create_vm(
        namespace=namespace.name,
        nad=bond_modes_nad,
        node_selector=worker_node1.name,
        unprivileged_client=unprivileged_client,
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def bridge_on_bond_fail_over_mac(
    bridge_device_matrix__class__,
    utility_pods,
    worker_node1,
    bond_modes_nad,
    active_backup_bond_with_fail_over_mac,
):
    """
    Create bridge and attach the BOND to it
    """
    with bridge_on_bond(
        interface_type=bridge_device_matrix__class__,
        utility_pods=utility_pods,
        node_selector=worker_node1.name,
        interface_name=bond_modes_nad.bridge_name,
        ports=[active_backup_bond_with_fail_over_mac.bond_name],
    ) as br:
        yield br


@pytest.fixture(scope="class")
def active_backup_bond_with_fail_over_mac(
    index_number, worker_node1, utility_pods, nodes_available_nics
):
    with create_bond(
        bond_idx=next(index_number),
        bond_ports=nodes_available_nics[worker_node1.name][-2:],
        worker_pods=utility_pods,
        mode="active-backup",
        node_selector=worker_node1.name,
        options={"fail_over_mac": "active"},
    ) as bond:
        yield bond


@pytest.fixture(scope="class")
def vm_with_fail_over_mac_bond(
    worker_node1,
    namespace,
    unprivileged_client,
    bond_modes_nad,
    active_backup_bond_with_fail_over_mac,
    bridge_on_bond_fail_over_mac,
):
    with create_vm(
        namespace=namespace.name,
        nad=bond_modes_nad,
        node_selector=worker_node1.name,
        unprivileged_client=unprivileged_client,
    ) as vm:
        yield vm


@pytest.mark.usefixtures("skip_no_bond_support", "skip_if_workers_bms")
class TestBondModes:
    @pytest.mark.polarion("CNV-4382")
    def test_bond_created(self, utility_pods, matrix_bond_modes_bond):
        assert_bond_validation(utility_pods=utility_pods, bond=matrix_bond_modes_bond)

    @pytest.mark.polarion("CNV-4383")
    def test_vm_started(self, bond_modes_vm):
        running_vm(
            vm=bond_modes_vm, check_ssh_connectivity=False, wait_for_interfaces=False
        )


@pytest.mark.usefixtures(
    "skip_no_bond_support",
    "skip_if_workers_bms",
)
class TestBondWithFailOverMac:
    @pytest.mark.polarion("CNV-6583")
    def test_active_backup_bond_with_fail_over_mac(
        self,
        index_number,
        worker_node1,
        nodes_available_nics,
        utility_pods,
    ):
        with create_bond(
            bond_idx=next(index_number),
            bond_ports=nodes_available_nics[worker_node1.name][-2:],
            worker_pods=utility_pods,
            mode="active-backup",
            node_selector=worker_node1.name,
            options={"fail_over_mac": "active"},
        ) as bond:
            assert_bond_validation(utility_pods=utility_pods, bond=bond)

    @pytest.mark.polarion("CNV-6584")
    def test_vm_bond_with_fail_over_mac_started(
        self,
        vm_with_fail_over_mac_bond,
    ):
        running_vm(
            vm=vm_with_fail_over_mac_bond,
            check_ssh_connectivity=False,
            wait_for_interfaces=False,
        )


@pytest.mark.polarion("CNV-7263")
def test_bond_with_slaves(
    index_number, worker_node1, nodes_available_nics, utility_pods
):
    bond_idx = next(index_number)
    with BondNodeNetworkConfigurationPolicyWithSlaves(
        name=f"bond{bond_idx}nncp",
        bond_name=f"bond{bond_idx}",
        bond_ports=nodes_available_nics[worker_node1.name][-2:],
        worker_pods=utility_pods,
        mode=BondNodeNetworkConfigurationPolicy.Mode.ACTIVE_BACKUP,
        mtu=1450,
        node_selector=worker_node1.hostname,
    ) as bond:
        # Since we override slave with port we must set it back after creation
        # for cleanup to work.
        bond.iface["link-aggregation"]["port"] = bond.iface["link-aggregation"].pop(
            "slaves"
        )
