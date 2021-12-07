"""
VM to VM connectivity over BOND with custom MTU (jumbo frame)
"""
from collections import OrderedDict

import pytest

from tests.network.utils import assert_no_ping
from utilities.constants import MTU_9000
from utilities.network import (
    BondNodeNetworkConfigurationPolicy,
    assert_ping_successful,
    cloud_init_network_data,
    get_vmi_ip_v4_by_name,
    network_device,
    network_nad,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


@pytest.fixture(scope="class")
def jumbo_frame_bond_name(index_number):
    yield f"jf-bond-{next(index_number)}"


@pytest.fixture(scope="class")
def jumbo_frame_bond1_worker_1(
    skip_no_bond_support,
    utility_pods,
    worker_node1,
    jumbo_frame_bond_name,
    nodes_available_nics,
):
    """
    Create BOND if setup support BOND
    """
    with BondNodeNetworkConfigurationPolicy(
        name=f"{jumbo_frame_bond_name}-nncp",
        bond_name=jumbo_frame_bond_name,
        bond_ports=nodes_available_nics[worker_node1.name][0:2],
        worker_pods=utility_pods,
        node_selector=worker_node1.name,
        mode="active-backup",
        mtu=MTU_9000,
    ) as bond:
        yield bond


@pytest.fixture(scope="class")
def jumbo_frame_bond1_worker_2(
    skip_no_bond_support,
    utility_pods,
    worker_node2,
    jumbo_frame_bond_name,
    nodes_available_nics,
):
    """
    Create BOND if setup support BOND
    """
    with BondNodeNetworkConfigurationPolicy(
        name=f"{jumbo_frame_bond_name}-nncp",
        bond_name=jumbo_frame_bond_name,
        bond_ports=nodes_available_nics[worker_node2.name][0:2],
        worker_pods=utility_pods,
        node_selector=worker_node2.name,
        mode="active-backup",
        mtu=MTU_9000,
    ) as bond:
        yield bond


@pytest.fixture(scope="class")
def jumbo_frame_bond_device_name(index_number):
    yield f"brbond{next(index_number)}test"


@pytest.fixture(scope="class")
def jumbo_frame_bridge_on_bond_worker_1(
    bridge_device_matrix__class__,
    jumbo_frame_bond1_worker_1,
    jumbo_frame_bond_device_name,
    utility_pods,
):
    """
    Create bridge and attach the BOND to it
    """
    with network_device(
        interface_type=bridge_device_matrix__class__,
        nncp_name="jumbo-frame-bridge-on-bond-1",
        interface_name=jumbo_frame_bond_device_name,
        network_utility_pods=utility_pods,
        node_selector=jumbo_frame_bond1_worker_1.node_selector,
        ports=[jumbo_frame_bond1_worker_1.bond_name],
        mtu=MTU_9000,
    ) as br:
        yield br


@pytest.fixture(scope="class")
def jumbo_frame_bridge_on_bond_worker_2(
    bridge_device_matrix__class__,
    jumbo_frame_bond1_worker_2,
    jumbo_frame_bond_device_name,
    utility_pods,
):
    """
    Create bridge and attach the BOND to it
    """
    with network_device(
        interface_type=bridge_device_matrix__class__,
        nncp_name="jumbo-frame-bridge-on-bond-2",
        interface_name=jumbo_frame_bond_device_name,
        network_utility_pods=utility_pods,
        node_selector=jumbo_frame_bond1_worker_2.node_selector,
        ports=[jumbo_frame_bond1_worker_2.bond_name],
        mtu=MTU_9000,
    ) as br:
        yield br


@pytest.fixture(scope="class")
def br1bond_nad(
    skip_no_bond_support,
    bridge_device_matrix__class__,
    namespace,
    jumbo_frame_bridge_on_bond_worker_1,
    jumbo_frame_bridge_on_bond_worker_2,
    jumbo_frame_bond_device_name,
):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name=f"{jumbo_frame_bond_device_name}-bond-nad",
        interface_name=f"{jumbo_frame_bond_device_name}-bond",
        mtu=MTU_9000,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def bond_bridge_attached_vma(
    worker_node1,
    namespace,
    unprivileged_client,
    br1bond_nad,
    jumbo_frame_bridge_on_bond_worker_1,
):
    name = "bond-vma"
    networks = OrderedDict()
    networks[br1bond_nad.name] = br1bond_nad.name
    network_data_data = {"ethernets": {"eth1": {"addresses": ["10.200.1.1/24"]}}}
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
def bond_bridge_attached_vmb(
    worker_node2,
    namespace,
    unprivileged_client,
    br1bond_nad,
    jumbo_frame_bridge_on_bond_worker_2,
):
    name = "bond-vmb"
    networks = OrderedDict()
    networks[br1bond_nad.name] = br1bond_nad.name
    network_data_data = {"ethernets": {"eth1": {"addresses": ["10.200.1.2/24"]}}}
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
def running_bond_bridge_attached_vma(bond_bridge_attached_vma):
    return running_vm(vm=bond_bridge_attached_vma)


@pytest.fixture(scope="class")
def running_bond_bridge_attached_vmb(bond_bridge_attached_vmb):
    return running_vm(vm=bond_bridge_attached_vmb)


class TestBondJumboFrame:
    @pytest.mark.polarion("CNV-3367")
    def test_connectivity_over_linux_bond_large_mtu(
        self,
        skip_if_workers_vms,
        skip_if_no_multinic_nodes,
        skip_when_one_node,
        skip_no_bond_support,
        namespace,
        jumbo_frame_bridge_on_bond_worker_1,
        jumbo_frame_bridge_on_bond_worker_2,
        br1bond_nad,
        bond_bridge_attached_vma,
        bond_bridge_attached_vmb,
        running_bond_bridge_attached_vma,
        running_bond_bridge_attached_vmb,
    ):
        """
        Check connectivity over linux bridge with custom MTU
        """
        icmp_header = 8
        ip_header = 20
        assert_ping_successful(
            src_vm=bond_bridge_attached_vma,
            dst_ip=get_vmi_ip_v4_by_name(
                vm=running_bond_bridge_attached_vmb, name=br1bond_nad.name
            ),
            packet_size=br1bond_nad.mtu - ip_header - icmp_header,
        )

    @pytest.mark.polarion("CNV-3368")
    def test_negative_mtu_linux_bond(
        self,
        skip_if_workers_vms,
        skip_if_no_multinic_nodes,
        skip_when_one_node,
        skip_no_bond_support,
        namespace,
        jumbo_frame_bridge_on_bond_worker_1,
        jumbo_frame_bridge_on_bond_worker_2,
        br1bond_nad,
        bond_bridge_attached_vma,
        bond_bridge_attached_vmb,
        running_bond_bridge_attached_vma,
        running_bond_bridge_attached_vmb,
    ):
        """
        Check connectivity failed when packet size is higher than custom MTU
        """
        assert_no_ping(
            src_vm=bond_bridge_attached_vma,
            dst_ip=get_vmi_ip_v4_by_name(
                vm=running_bond_bridge_attached_vmb, name=br1bond_nad.name
            ),
            packet_size=br1bond_nad.mtu + 100,
        )
