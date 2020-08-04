"""
VM to VM connectivity with  custom MTU (jumbo frame)
"""
from collections import OrderedDict

import pytest
from tests.network.utils import (
    assert_no_ping,
    assert_ping_successful,
    network_device,
    nmcli_add_con_cmds,
)
from utilities.infra import BUG_STATUS_CLOSED
from utilities.network import (
    BondNodeNetworkConfigurationPolicy,
    get_hosts_common_ports,
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
def bond1(skip_no_bond_support, utility_pods, nodes_active_nics):
    """
    Create BOND if setup support BOND
    """
    with BondNodeNetworkConfigurationPolicy(
        name="bond1nncp",
        bond_name="bond1",
        slaves=get_hosts_common_ports(nodes_active_nics=nodes_active_nics)[1:3],
        worker_pods=utility_pods,
        mode="active-backup",
        mtu=9000,
    ) as bond:
        yield bond


@pytest.fixture(scope="class")
def bridge_on_bond(
    bridge_device_matrix__class__, bond1, utility_pods, schedulable_nodes
):
    """
    Create bridge and attach the BOND to it
    """
    with network_device(
        interface_type=bridge_device_matrix__class__,
        nncp_name="bridge-on-bond",
        interface_name="br1bond",
        network_utility_pods=utility_pods,
        nodes=schedulable_nodes,
        ports=[bond1.bond_name],
    ) as br:
        yield br


@pytest.fixture(scope="class")
def nad(
    bridge_device_matrix__class__,
    namespace,
    utility_pods,
    nodes_active_nics,
    network_interface,
):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="br1test-nad",
        interface_name=network_interface.bridge_name,
        tuning=True,
        mtu=9000,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def br1bond_nad(skip_no_bond_support, bridge_device_matrix__class__, namespace):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="br1bond-nad",
        interface_name="br1bond",
        tuning=True,
        mtu=9000,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def bridge_attached_vma(worker_node1, namespace, unprivileged_client, nad):
    name = "vma"
    networks = OrderedDict()
    networks[nad.name] = nad.name

    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["bootcmd"] = nmcli_add_con_cmds(iface="eth1", ip="10.200.0.1")

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
def bridge_attached_vmb(worker_node2, namespace, unprivileged_client, nad):
    name = "vmb"
    networks = OrderedDict()
    networks[nad.name] = nad.name

    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["bootcmd"] = nmcli_add_con_cmds(iface="eth1", ip="10.200.0.2")

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
def bond_bridge_attached_vma(
    worker_node1, namespace, unprivileged_client, br1bond_nad, bridge_on_bond
):
    name = "bond-vma"
    networks = OrderedDict()
    networks[br1bond_nad.name] = br1bond_nad.name

    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["bootcmd"] = nmcli_add_con_cmds(iface="eth1", ip="10.200.1.1")

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
    worker_node2, namespace, unprivileged_client, br1bond_nad, bridge_on_bond
):
    name = "bond-vmb"
    networks = OrderedDict()
    networks[br1bond_nad.name] = br1bond_nad.name

    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["bootcmd"] = nmcli_add_con_cmds(iface="eth1", ip="10.200.1.2")

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
def running_bridge_attached_vmia(bridge_attached_vma):
    vmi = bridge_attached_vma.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    return vmi


@pytest.fixture(scope="class")
def running_bridge_attached_vmib(bridge_attached_vmb):
    vmi = bridge_attached_vmb.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    return vmi


@pytest.fixture(scope="class")
def running_bond_bridge_attached_vmia(bond_bridge_attached_vma):
    vmi = bond_bridge_attached_vma.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    return vmi


@pytest.fixture(scope="class")
def running_bond_bridge_attached_vmib(bond_bridge_attached_vmb):
    vmi = bond_bridge_attached_vmb.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    return vmi


@pytest.mark.bugzilla(
    1814614, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)
@pytest.mark.usefixtures("skip_rhel7_workers")
@pytest.mark.parametrize("network_interface", [{"mtu": 9000}], indirect=True)
class TestJumboFrame:
    @pytest.mark.polarion("CNV-2685")
    def test_connectivity_over_linux_bridge_large_mtu(
        self,
        skip_if_workers_vms,
        skip_if_no_multinic_nodes,
        skip_when_one_node,
        network_interface,
        namespace,
        nad,
        bridge_attached_vma,
        bridge_attached_vmb,
        running_bridge_attached_vmia,
        running_bridge_attached_vmib,
    ):
        """
        Check connectivity over linux bridge with custom MTU
        """
        icmp_header = 8
        ip_header = 20
        assert_ping_successful(
            src_vm=bridge_attached_vma,
            dst_ip=get_vmi_ip_v4_by_name(
                vmi=running_bridge_attached_vmib, name=nad.name
            ),
            packetsize=nad.mtu - ip_header - icmp_header,
        )

    @pytest.mark.polarion("CNV-3788")
    def test_negative_mtu_linux_bridge(
        self,
        skip_if_workers_vms,
        skip_if_no_multinic_nodes,
        skip_when_one_node,
        network_interface,
        namespace,
        nad,
        bridge_attached_vma,
        bridge_attached_vmb,
        running_bridge_attached_vmia,
        running_bridge_attached_vmib,
    ):
        """
        Check connectivity failed when packet size is higher than custom MTU
        """
        assert_no_ping(
            src_vm=bridge_attached_vma,
            dst_ip=get_vmi_ip_v4_by_name(
                vmi=running_bridge_attached_vmib, name=nad.name
            ),
            packetsize=nad.mtu + 100,
        )


@pytest.mark.bugzilla(
    1814614, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)
@pytest.mark.usefixtures("skip_rhel7_workers")
class TestBondJumboFrame:
    @pytest.mark.polarion("CNV-3367")
    def test_connectivity_over_linux_bond_large_mtu(
        self,
        skip_if_workers_vms,
        skip_if_no_multinic_nodes,
        skip_when_one_node,
        skip_no_bond_support,
        namespace,
        bridge_on_bond,
        br1bond_nad,
        bond_bridge_attached_vma,
        bond_bridge_attached_vmb,
        running_bond_bridge_attached_vmia,
        running_bond_bridge_attached_vmib,
    ):
        """
        Check connectivity over linux bridge with custom MTU
        """
        icmp_header = 8
        ip_header = 20
        assert_ping_successful(
            src_vm=bond_bridge_attached_vma,
            dst_ip=get_vmi_ip_v4_by_name(
                vmi=running_bond_bridge_attached_vmib, name=br1bond_nad.name
            ),
            packetsize=br1bond_nad.mtu - ip_header - icmp_header,
        )

    @pytest.mark.polarion("CNV-3368")
    def test_negative_mtu_linux_bond(
        self,
        skip_if_workers_vms,
        skip_if_no_multinic_nodes,
        skip_when_one_node,
        skip_no_bond_support,
        namespace,
        bridge_on_bond,
        br1bond_nad,
        bond_bridge_attached_vma,
        bond_bridge_attached_vmb,
        running_bond_bridge_attached_vmia,
        running_bond_bridge_attached_vmib,
    ):
        """
        Check connectivity failed when packet size is higher than custom MTU
        """
        assert_no_ping(
            src_vm=bond_bridge_attached_vma,
            dst_ip=get_vmi_ip_v4_by_name(
                vmi=running_bond_bridge_attached_vmib, name=br1bond_nad.name
            ),
            packetsize=br1bond_nad.mtu + 100,
        )
