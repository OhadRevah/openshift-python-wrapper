"""
VM to VM connectivity
"""

import pytest
from pytest_testconfig import config as py_config
from tests.network.connectivity.utils import (
    BondNodeNetworkConfigurationPolicy,
    run_test_guest_performance,
)
from tests.network.utils import (
    assert_no_ping,
    assert_ping_successful,
    bridge_device,
    bridge_nad,
    get_vmi_ip_v4_by_name,
    nmcli_add_con_cmds,
)
from utilities.infra import BUG_STATUS_CLOSED
from utilities.network import LinuxBridgeNodeNetworkConfigurationPolicy
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


@pytest.fixture(scope="module")
def nad(bridge_device_matrix, namespace):
    with bridge_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix,
        nad_name="br1test-nad",
        bridge_name="br1test",
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def br1test(
    bridge_device_matrix,
    multi_nics_nodes,
    ovs_worker_pods,
    schedulable_node_ips,
    namespace,
    network_utility_pods,
    nodes_active_nics,
    nad,
):
    ports = (
        [nodes_active_nics[network_utility_pods[0].node.name][1]]
        if multi_nics_nodes
        else []
    )
    with bridge_device(
        bridge_type=bridge_device_matrix,
        nncp_name=f"{nad.bridge_name}-nncp",
        bridge_name=nad.bridge_name,
        network_utility_pods=network_utility_pods,
        ports=ports,
        ovs_worker_pods=ovs_worker_pods,
        nodes_active_nics=nodes_active_nics,
        schedulable_node_ips=schedulable_node_ips,
        idx=100,
    ) as br:
        yield br


@pytest.fixture(scope="module")
def br1vlan100_nad(bridge_device_matrix, namespace, br1test):
    with bridge_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix,
        nad_name="br1vlan100-nad",
        bridge_name=br1test.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def br1vlan200_nad(bridge_device_matrix, namespace, br1test):
    with bridge_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix,
        nad_name="br1vlan200-nad",
        bridge_name=br1test.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def br1vlan300_nad(bridge_device_matrix, namespace, br1test):
    with bridge_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix,
        nad_name="br1vlan300-nad",
        bridge_name=br1test.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def bond1(network_utility_pods, bond_supported, nodes_active_nics):
    """
    Create BOND if setup support BOND
    """
    bond_name = "bond1"
    if bond_supported:
        with BondNodeNetworkConfigurationPolicy(
            name="bond1nncp",
            bond_name=bond_name,
            nodes=[i.node.name for i in network_utility_pods],
            nics=nodes_active_nics[network_utility_pods[0].node.name][2:4],
        ):
            yield bond_name
    else:
        yield None


@pytest.fixture(scope="module")
def bridge_on_bond(bond1, network_utility_pods):
    """
    Create bridge and attach the BOND to it
    """
    if bond1:
        with LinuxBridgeNodeNetworkConfigurationPolicy(
            name="bridge-no-bond",
            bridge_name="br1bond",
            worker_pods=network_utility_pods,
            ports=[bond1],
        ) as br:
            yield br
    else:
        yield


@pytest.fixture(scope="module")
def bridge_attached_vma(
    nodes,
    bridge_on_bond,
    namespace,
    unprivileged_client,
    nad,
    br1vlan100_nad,
    br1vlan200_nad,
):
    name = "vma"
    networks = {
        nad.name: nad.name,
        br1vlan100_nad.name: br1vlan100_nad.name,
        br1vlan200_nad.name: br1vlan200_nad.name,
    }
    bootcmds = []
    bootcmds.extend(nmcli_add_con_cmds("eth1", "192.168.0.1"))
    bootcmds.extend(nmcli_add_con_cmds("eth2", "192.168.1.1"))
    bootcmds.extend(nmcli_add_con_cmds("eth3", "192.168.2.1"))
    if bridge_on_bond:
        bootcmds.extend(nmcli_add_con_cmds("eth4", "192.168.3.1"))
        networks[bridge_on_bond.bridge_name] = bridge_on_bond.bridge_name

    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["bootcmd"] = bootcmds

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name),
        networks=networks,
        interfaces=sorted(networks.keys()),
        node_selector=nodes[0].name,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def bridge_attached_vmb(
    nodes,
    bridge_on_bond,
    namespace,
    unprivileged_client,
    nad,
    br1vlan100_nad,
    br1vlan300_nad,
):
    name = "vmb"
    networks = {
        nad.name: nad.name,
        br1vlan100_nad.name: br1vlan100_nad.name,
        br1vlan300_nad.name: br1vlan300_nad.name,
    }
    bootcmds = []
    bootcmds.extend(nmcli_add_con_cmds("eth1", "192.168.0.2"))
    bootcmds.extend(nmcli_add_con_cmds("eth2", "192.168.1.2"))
    bootcmds.extend(nmcli_add_con_cmds("eth3", "192.168.2.2"))
    if bridge_on_bond:
        bootcmds.extend(nmcli_add_con_cmds("eth4", "192.168.3.2"))
        networks[bridge_on_bond.bridge_name] = bridge_on_bond.bridge_name

    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["bootcmd"] = bootcmds

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name),
        networks=networks,
        interfaces=sorted(networks.keys()),
        node_selector=nodes[1].name,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def running_bridge_attached_vmia(bridge_attached_vma):
    vmi = bridge_attached_vma.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    return vmi


@pytest.fixture(scope="module")
def running_bridge_attached_vmib(bridge_attached_vmb):
    vmi = bridge_attached_vmb.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    return vmi


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
def test_connectivity(
    bridge,
    skip_when_one_node,
    namespace,
    br1test,
    bridge_attached_vma,
    bridge_attached_vmb,
    running_bridge_attached_vmia,
    running_bridge_attached_vmib,
):
    assert_ping_successful(
        src_vm=running_bridge_attached_vmia,
        dst_ip=_masquerade_vmib_ip(running_bridge_attached_vmib, bridge),
    )


@pytest.mark.polarion("CNV-2141")
def test_connectivity_bond(
    skip_when_one_node,
    namespace,
    br1test,
    bridge_on_bond,
    bridge_attached_vma,
    bridge_attached_vmb,
    running_bridge_attached_vmia,
    running_bridge_attached_vmib,
):
    if not bridge_on_bond:
        pytest.skip(msg="No BOND support")

    assert_ping_successful(
        src_vm=running_bridge_attached_vmia,
        dst_ip=get_vmi_ip_v4_by_name(
            vmi=running_bridge_attached_vmib, name=bridge_on_bond.bridge_name
        ),
    )


@pytest.mark.polarion("CNV-2072")
def test_connectivity_positive_vlan(
    skip_not_bare_metal,
    skip_when_one_node,
    namespace,
    br1test,
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
def test_connectivity_negative_vlan(
    skip_not_bare_metal,
    skip_when_one_node,
    namespace,
    br1test,
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
    skip_not_bare_metal,
    skip_when_one_node,
    namespace,
    br1test,
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
