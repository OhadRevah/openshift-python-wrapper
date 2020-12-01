"""
Connectivity over bond bridge on secondary interface
"""
from collections import OrderedDict

import pytest

import tests.network.utils as network_utils
from utilities.network import (
    BondNodeNetworkConfigurationPolicy,
    assert_ping_successful,
    cloud_init_network_data,
    get_vmi_ip_v4_by_name,
    network_nad,
)
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


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
def ovs_linux_bond1(
    index_number,
    utility_pods,
    hosts_common_available_ports,
    link_aggregation_mode_matrix__class__,
):
    """
    Create BOND if setup support BOND
    """
    bond_idx = next(index_number)
    with BondNodeNetworkConfigurationPolicy(
        name=f"bond{bond_idx}nncp",
        bond_name=f"bond{bond_idx}",
        slaves=hosts_common_available_ports[0:2],
        worker_pods=utility_pods,
        mode=link_aggregation_mode_matrix__class__,
        mtu=1450,
    ) as bond:
        yield bond


@pytest.fixture(scope="class")
def ovs_linux_bridge_on_bond(
    bridge_device_matrix__class__,
    utility_pods,
    schedulable_nodes,
    ovs_linux_br1bond_nad,
    ovs_linux_bond1,
):
    """
    Create bridge and attach the BOND to it
    """
    with network_utils.network_device(
        interface_type=bridge_device_matrix__class__,
        nncp_name="bridge-on-bond",
        interface_name=ovs_linux_br1bond_nad.bridge_name,
        network_utility_pods=utility_pods,
        nodes=schedulable_nodes,
        ports=[ovs_linux_bond1.bond_name],
    ) as br:
        yield br


@pytest.fixture(scope="class")
def ovs_linux_bond_bridge_attached_vma(
    worker_node1,
    namespace,
    unprivileged_client,
    ovs_linux_br1bond_nad,
    ovs_linux_bridge_on_bond,
):
    name = "bond-vma"
    networks = OrderedDict()
    networks[ovs_linux_br1bond_nad.name] = ovs_linux_br1bond_nad.name
    network_data_data = {"ethernets": {"eth1": {"addresses": ["10.200.3.1/24"]}}}
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data.update(cloud_init_network_data(data=network_data_data))

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
    ovs_linux_bridge_on_bond,
):
    name = "bond-vmb"
    networks = OrderedDict()
    networks[ovs_linux_br1bond_nad.name] = ovs_linux_br1bond_nad.name
    network_data_data = {"ethernets": {"eth1": {"addresses": ["10.200.3.2/24"]}}}
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data.update(cloud_init_network_data(data=network_data_data))

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
def ovs_linux_bond_bridge_attached_running_vmia(ovs_linux_bond_bridge_attached_vma):
    vmi = ovs_linux_bond_bridge_attached_vma.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    return vmi


@pytest.fixture(scope="class")
def ovs_linux_bond_bridge_attached_running_vmib(ovs_linux_bond_bridge_attached_vmb):
    vmi = ovs_linux_bond_bridge_attached_vmb.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    return vmi


class TestBondConnectivity:
    @pytest.mark.polarion("CNV-3366")
    def test_bond(
        self,
        skip_rhel7_workers,
        skip_no_bond_support,
        namespace,
        ovs_linux_br1bond_nad,
        ovs_linux_bridge_on_bond,
        ovs_linux_bond_bridge_attached_vma,
        ovs_linux_bond_bridge_attached_vmb,
        ovs_linux_bond_bridge_attached_running_vmia,
        ovs_linux_bond_bridge_attached_running_vmib,
    ):
        assert_ping_successful(
            src_vm=ovs_linux_bond_bridge_attached_running_vmia,
            dst_ip=get_vmi_ip_v4_by_name(
                vmi=ovs_linux_bond_bridge_attached_running_vmib,
                name=ovs_linux_br1bond_nad.name,
            ),
        )
