"""
Connectivity over bond bridge on secondary interface
"""
from collections import OrderedDict

import pytest

from utilities.network import (
    BondNodeNetworkConfigurationPolicy,
    assert_ping_successful,
    cloud_init_network_data,
    get_vmi_ip_v4_by_name,
)
from utilities.network import network_device_nocm as network_device
from utilities.network import network_nad_nocm as network_nad
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


@pytest.fixture(scope="class")
def ovs_linux_br1bond_nad(bridge_device_matrix__class__, namespace):
    nad = network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="br1bond-nad",
        interface_name="br1bond",
    )
    nad.deploy()
    yield nad
    nad.clean_up()


@pytest.fixture(scope="class")
def ovs_linux_bond1_worker_1(
    index_number,
    utility_pods,
    worker_node1,
    nodes_available_nics,
    link_aggregation_mode_matrix__class__,
):
    """
    Create BOND if setup support BOND
    """
    bond_idx = next(index_number)
    bond = BondNodeNetworkConfigurationPolicy(
        name=f"bond{bond_idx}nncp",
        bond_name=f"bond{bond_idx}",
        slaves=nodes_available_nics[worker_node1.name][0:2],
        worker_pods=utility_pods,
        node_selector=worker_node1.name,
        mode=link_aggregation_mode_matrix__class__,
        mtu=1450,
    )
    bond.deploy()
    yield bond
    bond.clean_up()


@pytest.fixture(scope="class")
def ovs_linux_bond1_worker_2(
    index_number,
    utility_pods,
    worker_node2,
    nodes_available_nics,
    link_aggregation_mode_matrix__class__,
    ovs_linux_bond1_worker_1,
):
    """
    Create BOND if setup support BOND
    """
    bond_idx = next(index_number)
    bond = BondNodeNetworkConfigurationPolicy(
        name=f"bond{bond_idx}nncp",
        bond_name=ovs_linux_bond1_worker_1.bond_name,  # Use the same BOND name for each test.
        slaves=nodes_available_nics[worker_node2.name][0:2],
        worker_pods=utility_pods,
        node_selector=worker_node2.name,
        mode=link_aggregation_mode_matrix__class__,
        mtu=1450,
    )
    bond.deploy()
    yield bond
    bond.clean_up()


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
    br = network_device(
        interface_type=bridge_device_matrix__class__,
        nncp_name="bridge-on-bond-worker-1",
        interface_name=ovs_linux_br1bond_nad.bridge_name,
        network_utility_pods=utility_pods,
        node_selector=worker_node1.name,
        ports=[ovs_linux_bond1_worker_1.bond_name],
    )
    br.deploy()
    yield br
    br.clean_up()


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
    br = network_device(
        interface_type=bridge_device_matrix__class__,
        nncp_name="bridge-on-bond-worker-2",
        interface_name=ovs_linux_br1bond_nad.bridge_name,
        network_utility_pods=utility_pods,
        node_selector=worker_node2.name,
        ports=[ovs_linux_bond1_worker_2.bond_name],
    )
    br.deploy()
    yield br
    br.clean_up()


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
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data.update(cloud_init_network_data(data=network_data_data))

    vm = VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=worker_node1.name,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    )
    vm.deploy()
    vm.start(wait=True)
    yield vm
    vm.clean_up()


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
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data.update(cloud_init_network_data(data=network_data_data))

    vm = VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=worker_node2.name,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    )
    vm.deploy()
    vm.start(wait=True)
    yield vm
    vm.clean_up()


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
        ovs_linux_bridge_on_bond_worker_1,
        ovs_linux_bridge_on_bond_worker_2,
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
