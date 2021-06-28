"""
Connectivity over bond bridge on secondary interface
"""
from collections import OrderedDict

import pytest

import utilities.network
from utilities.infra import (
    BUG_STATUS_CLOSED,
    get_bug_status,
    get_bugzilla_connection_params,
)
from utilities.network import (
    BondNodeNetworkConfigurationPolicy,
    assert_ping_successful,
    cloud_init_network_data,
    get_vmi_ip_v4_by_name,
    network_nad,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


@pytest.fixture(scope="class")
def skip_bond_mode_balance_tlb_with_bz(link_aggregation_mode_matrix__class__):
    bug_id = 1972705
    if (
        link_aggregation_mode_matrix__class__ == "balance-tlb"
        and get_bug_status(
            bugzilla_connection_params=get_bugzilla_connection_params(), bug=bug_id
        )
        not in BUG_STATUS_CLOSED
    ):
        pytest.skip(msg=f"Skip test: bug {bug_id}")


@pytest.fixture(scope="class")
def ovs_linux_br1bond_nad(bridge_device_matrix__class__, namespace):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="br1bond-nad",
        interface_name="br1bond",
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def ovs_linux_bond1_worker_1(
    skip_bond_mode_balance_tlb_with_bz,
    link_aggregation_mode_matrix__class__,
    index_number,
    utility_pods,
    worker_node1,
    nodes_available_nics,
):
    """
    Create BOND if setup support BOND
    """
    bond_idx = next(index_number)
    with BondNodeNetworkConfigurationPolicy(
        name=f"bond{bond_idx}nncp-worker-1",
        bond_name=f"bond{bond_idx}",
        slaves=nodes_available_nics[worker_node1.name][0:2],
        worker_pods=utility_pods,
        node_selector=worker_node1.name,
        mode=link_aggregation_mode_matrix__class__,
        mtu=1450,
    ) as bond:
        yield bond


@pytest.fixture(scope="class")
def ovs_linux_bond1_worker_2(
    skip_bond_mode_balance_tlb_with_bz,
    link_aggregation_mode_matrix__class__,
    index_number,
    utility_pods,
    worker_node2,
    nodes_available_nics,
    ovs_linux_bond1_worker_1,
):
    """
    Create BOND if setup support BOND
    """
    bond_idx = next(index_number)
    with BondNodeNetworkConfigurationPolicy(
        name=f"bond{bond_idx}nncp-worker-2",
        bond_name=ovs_linux_bond1_worker_1.bond_name,  # Use the same BOND name for each test.
        slaves=nodes_available_nics[worker_node2.name][0:2],
        worker_pods=utility_pods,
        node_selector=worker_node2.name,
        mode=link_aggregation_mode_matrix__class__,
        mtu=1450,
    ) as bond:
        yield bond


@pytest.fixture(scope="class")
def ovs_linux_bridge_on_bond_worker_1(
    bridge_device_matrix__class__,
    utility_pods,
    worker_node1,
    ovs_linux_br1bond_nad,
    ovs_linux_bond1_worker_1,
):
    """
    Create bridge and attach the BOND to it
    """
    with utilities.network.network_device(
        interface_type=bridge_device_matrix__class__,
        nncp_name="bridge-on-bond-worker-1",
        interface_name=ovs_linux_br1bond_nad.bridge_name,
        network_utility_pods=utility_pods,
        node_selector=worker_node1.name,
        ports=[ovs_linux_bond1_worker_1.bond_name],
    ) as br:
        yield br


@pytest.fixture(scope="class")
def ovs_linux_bridge_on_bond_worker_2(
    bridge_device_matrix__class__,
    utility_pods,
    worker_node2,
    ovs_linux_br1bond_nad,
    ovs_linux_bond1_worker_2,
):
    """
    Create bridge and attach the BOND to it
    """
    with utilities.network.network_device(
        interface_type=bridge_device_matrix__class__,
        nncp_name="bridge-on-bond-worker-2",
        interface_name=ovs_linux_br1bond_nad.bridge_name,
        network_utility_pods=utility_pods,
        node_selector=worker_node2.name,
        ports=[ovs_linux_bond1_worker_2.bond_name],
    ) as br:
        yield br


@pytest.fixture(scope="class")
def ovs_linux_bond_bridge_attached_vma(
    worker_node1,
    namespace,
    unprivileged_client,
    ovs_linux_br1bond_nad,
    ovs_linux_bridge_on_bond_worker_1,
):
    name = "bond-vma"
    networks = OrderedDict()
    networks[ovs_linux_br1bond_nad.name] = ovs_linux_br1bond_nad.name
    network_data_data = {"ethernets": {"eth1": {"addresses": ["10.200.3.1/24"]}}}
    cloud_init_data = cloud_init_network_data(data=network_data_data)

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=worker_node1.name,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="class")
def ovs_linux_bond_bridge_attached_vmb(
    worker_node2,
    namespace,
    unprivileged_client,
    ovs_linux_br1bond_nad,
    ovs_linux_bridge_on_bond_worker_2,
):
    name = "bond-vmb"
    networks = OrderedDict()
    networks[ovs_linux_br1bond_nad.name] = ovs_linux_br1bond_nad.name
    network_data_data = {"ethernets": {"eth1": {"addresses": ["10.200.3.2/24"]}}}
    cloud_init_data = cloud_init_network_data(data=network_data_data)

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=worker_node2.name,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="class")
def ovs_linux_bond_bridge_attached_running_vma(ovs_linux_bond_bridge_attached_vma):
    return running_vm(vm=ovs_linux_bond_bridge_attached_vma)


@pytest.fixture(scope="class")
def ovs_linux_bond_bridge_attached_running_vmb(ovs_linux_bond_bridge_attached_vmb):
    return running_vm(vm=ovs_linux_bond_bridge_attached_vmb)


@pytest.mark.usefixtures("skip_if_workers_bms")
class TestBondConnectivity:
    @pytest.mark.polarion("CNV-3366")
    def test_bond(
        self,
        skip_no_bond_support,
        namespace,
        ovs_linux_br1bond_nad,
        ovs_linux_bridge_on_bond_worker_1,
        ovs_linux_bridge_on_bond_worker_2,
        ovs_linux_bond_bridge_attached_vma,
        ovs_linux_bond_bridge_attached_vmb,
        ovs_linux_bond_bridge_attached_running_vma,
        ovs_linux_bond_bridge_attached_running_vmb,
    ):
        assert_ping_successful(
            src_vm=ovs_linux_bond_bridge_attached_running_vma,
            dst_ip=get_vmi_ip_v4_by_name(
                vm=ovs_linux_bond_bridge_attached_running_vmb,
                name=ovs_linux_br1bond_nad.name,
            ),
        )
