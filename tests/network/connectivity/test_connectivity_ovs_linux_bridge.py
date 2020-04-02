"""
VM to VM connectivity
"""
from collections import OrderedDict

import pytest
import tests.network.utils as network_utils
from pytest_testconfig import config as py_config
from tests.network.connectivity.utils import run_test_guest_performance
from tests.network.utils import (
    assert_no_ping,
    assert_ping_successful,
    bridge_nad,
    nmcli_add_con_cmds,
)
from utilities.infra import BUG_STATUS_CLOSED
from utilities.network import BondNodeNetworkConfigurationPolicy, get_vmi_ip_v4_by_name
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


def _masquerade_vmib_ip(vmib, bridge):
    # Using masquerade we can just ping vmb pods ip
    masquerade_interface = [
        i
        for i in vmib.instance.spec.domain.devices.interfaces
        if i["name"] == bridge and "masquerade" in i.keys()
    ]
    if masquerade_interface:
        return vmib.virt_launcher_pod.instance.status.podIP

    return get_vmi_ip_v4_by_name(vmi=vmib, name=bridge)


@pytest.fixture(scope="class")
def nad(bridge_device_matrix__class__, namespace, ovs_lb_bridge):
    with bridge_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="br1test-nad",
        bridge_name=ovs_lb_bridge.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def br1vlan100_nad(bridge_device_matrix__class__, namespace, ovs_lb_bridge):
    with bridge_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="br1vlan100-nad",
        bridge_name=ovs_lb_bridge.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def br1vlan200_nad(bridge_device_matrix__class__, namespace, ovs_lb_bridge):
    with bridge_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="br1vlan200-nad",
        bridge_name=ovs_lb_bridge.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def br1vlan300_nad(bridge_device_matrix__class__, namespace, ovs_lb_bridge):
    with bridge_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="br1vlan300-nad",
        bridge_name=ovs_lb_bridge.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def br1bond_nad(bridge_device_matrix__class__, namespace):
    with bridge_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="br1bond-nad",
        bridge_name="br1bond",
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def bond1(
    network_utility_pods, nodes_active_nics, link_aggregation_mode_matrix__class__,
):
    """
    Create BOND if setup support BOND
    """
    with BondNodeNetworkConfigurationPolicy(
        name="bond1nncp",
        bond_name="bond1",
        nodes=[i.node.name for i in network_utility_pods],
        nics=nodes_active_nics[network_utility_pods[0].node.name][2:4],
        worker_pods=network_utility_pods,
        mode=link_aggregation_mode_matrix__class__,
        mtu=1450,
    ) as bond:
        yield bond


@pytest.fixture(scope="class")
def bridge_on_bond(
    bridge_device_matrix__class__,
    network_utility_pods,
    schedulable_nodes,
    br1bond_nad,
    bond1,
):
    """
    Create bridge and attach the BOND to it
    """
    with network_utils.bridge_device(
        bridge_type=bridge_device_matrix__class__,
        nncp_name="bridge-on-bond",
        bridge_name=br1bond_nad.bridge_name,
        network_utility_pods=network_utility_pods,
        nodes=schedulable_nodes,
        ports=[bond1.bond_name],
    ) as br:
        yield br


@pytest.fixture(scope="class")
def bridge_attached_vma(
    schedulable_nodes,
    namespace,
    unprivileged_client,
    nad,
    br1vlan100_nad,
    br1vlan200_nad,
):
    name = "vma"
    networks = OrderedDict()
    networks[nad.name] = nad.name
    networks[br1vlan100_nad.name] = br1vlan100_nad.name
    networks[br1vlan200_nad.name] = br1vlan200_nad.name
    bootcmds = []
    bootcmds.extend(nmcli_add_con_cmds("eth1", "192.168.0.1"))
    bootcmds.extend(nmcli_add_con_cmds("eth2", "192.168.1.1"))
    bootcmds.extend(nmcli_add_con_cmds("eth3", "192.168.2.1"))
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["bootcmd"] = bootcmds

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=schedulable_nodes[0].name,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="class")
def bridge_attached_vmb(
    schedulable_nodes,
    namespace,
    unprivileged_client,
    nad,
    br1vlan100_nad,
    br1vlan300_nad,
):
    name = "vmb"
    networks = OrderedDict()
    networks[nad.name] = nad.name
    networks[br1vlan100_nad.name] = br1vlan100_nad.name
    networks[br1vlan300_nad.name] = br1vlan300_nad.name
    bootcmds = []
    bootcmds.extend(nmcli_add_con_cmds("eth1", "192.168.0.2"))
    bootcmds.extend(nmcli_add_con_cmds("eth2", "192.168.1.2"))
    bootcmds.extend(nmcli_add_con_cmds("eth3", "192.168.2.2"))
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["bootcmd"] = bootcmds

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=schedulable_nodes[1].name,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="class")
def bond_bridge_attached_vma(
    schedulable_nodes, namespace, unprivileged_client, br1bond_nad, bridge_on_bond,
):
    name = "bond-vma"
    networks = OrderedDict()
    networks[br1bond_nad.name] = br1bond_nad.name

    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["bootcmd"] = nmcli_add_con_cmds("eth1", "192.168.3.1")

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=schedulable_nodes[0].name,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="class")
def bond_bridge_attached_vmb(
    schedulable_nodes, namespace, unprivileged_client, br1bond_nad, bridge_on_bond,
):
    name = "bond-vmb"
    networks = OrderedDict()
    networks[br1bond_nad.name] = br1bond_nad.name

    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["bootcmd"] = nmcli_add_con_cmds("eth1", "192.168.3.2")

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=schedulable_nodes[1].name,
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


@pytest.mark.usefixtures("skip_rhel7_workers", "skip_when_one_node")
class TestConnectivity:
    @pytest.mark.parametrize(
        "bridge",
        [
            pytest.param(
                "default",
                marks=(pytest.mark.polarion("CNV-2350")),
                id="Connectivity_between_VM_to_VM_over_POD_network_make_sure_it_works_while_L2_networks_exists",
            ),
            pytest.param(
                "br1test-nad",
                marks=(pytest.mark.polarion("CNV-2080")),
                id="Connectivity_between_VM_to_VM_over_L2_bridge_network",
            ),
        ],
    )
    def test_bridge(
        self,
        bridge,
        rhel7_workers,
        namespace,
        ovs_lb_bridge,
        bridge_attached_vma,
        bridge_attached_vmb,
        running_bridge_attached_vmia,
        running_bridge_attached_vmib,
    ):
        if bridge == "default" and rhel7_workers:
            # https://bugzilla.redhat.com/show_bug.cgi?id=1787576
            pytest.skip(msg="Masquerade not working on RHEL7 workers.")

        assert_ping_successful(
            src_vm=running_bridge_attached_vmia,
            dst_ip=_masquerade_vmib_ip(running_bridge_attached_vmib, bridge),
        )

    @pytest.mark.polarion("CNV-2072")
    def test_positive_vlan(
        self,
        skip_rhel7_workers,
        skip_if_workers_vms,
        namespace,
        ovs_lb_bridge,
        br1vlan100_nad,
        bridge_attached_vma,
        bridge_attached_vmb,
        running_bridge_attached_vmia,
        running_bridge_attached_vmib,
    ):
        assert_ping_successful(
            src_vm=running_bridge_attached_vmia,
            dst_ip=get_vmi_ip_v4_by_name(
                vmi=running_bridge_attached_vmib, name=br1vlan100_nad.name
            ),
        )

    @pytest.mark.bugzilla(
        1758917, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    @pytest.mark.polarion("CNV-2075")
    def test_negative_vlan(
        self,
        skip_rhel7_workers,
        skip_if_workers_vms,
        namespace,
        ovs_lb_bridge,
        br1vlan300_nad,
        bridge_attached_vma,
        bridge_attached_vmb,
        running_bridge_attached_vmia,
        running_bridge_attached_vmib,
    ):
        assert_no_ping(
            src_vm=running_bridge_attached_vmia,
            dst_ip=get_vmi_ip_v4_by_name(
                vmi=running_bridge_attached_vmib, name=br1vlan300_nad.name
            ),
        )

    @pytest.mark.xfail(reason="Slow performance on BM, need investigation")
    @pytest.mark.polarion("CNV-2335")
    def test_guest_performance(
        self,
        skip_rhel7_workers,
        skip_if_workers_vms,
        namespace,
        ovs_lb_bridge,
        nad,
        bridge_attached_vma,
        bridge_attached_vmb,
        running_bridge_attached_vmia,
        running_bridge_attached_vmib,
    ):
        """
        In-guest performance bandwidth passthrough.
        """
        expected_res = py_config["test_guest_performance"]["bandwidth"]
        bits_per_second = run_test_guest_performance(
            server_vm=bridge_attached_vma,
            client_vm=bridge_attached_vmb,
            listen_ip=get_vmi_ip_v4_by_name(
                vmi=running_bridge_attached_vmia, name=nad.name
            ),
        )
        assert bits_per_second >= expected_res


class TestBondConnectivity:
    @pytest.mark.polarion("CNV-3366")
    def test_bond(
        self,
        skip_rhel7_workers,
        skip_no_bond_support,
        namespace,
        br1bond_nad,
        bridge_on_bond,
        bond_bridge_attached_vma,
        bond_bridge_attached_vmb,
        running_bond_bridge_attached_vmia,
        running_bond_bridge_attached_vmib,
    ):
        assert_ping_successful(
            src_vm=running_bond_bridge_attached_vmia,
            dst_ip=get_vmi_ip_v4_by_name(
                vmi=running_bond_bridge_attached_vmib, name=br1bond_nad.name
            ),
        )
