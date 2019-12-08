"""
VM to VM connectivity with  custom MTU (jumbo frame)
"""

import pytest
from tests.network.utils import (
    assert_ping_successful,
    bridge_device,
    bridge_nad,
    get_vmi_ip_v4_by_name,
    nmcli_add_con_cmds,
)
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


@pytest.fixture(scope="module")
def nad(bridge_device_matrix, namespace, network_utility_pods, nodes_active_nics):
    with bridge_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix,
        nad_name="br1test-nad",
        bridge_name="br1test",
        tuning=True,
        mtu=9000,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def bridge(bridge_device_matrix, network_utility_pods, nodes_active_nics, nad):
    ports = [nodes_active_nics[network_utility_pods[0].node.name][1]]
    with bridge_device(
        bridge_type=bridge_device_matrix,
        nncp_name=f"{nad.bridge_name}-nncp",
        bridge_name=nad.bridge_name,
        network_utility_pods=network_utility_pods,
        ports=ports,
        mtu=nad.mtu,
    ) as br:
        yield br


@pytest.fixture(scope="module")
def bridge_attached_vma(nodes, namespace, unprivileged_client, nad):
    name = "vma"
    networks = {nad.name: nad.name}
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["bootcmd"] = nmcli_add_con_cmds("eth1", "192.168.0.1")

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name),
        networks=networks,
        interfaces=sorted(networks.keys()),
        node_selector=nodes[0].name,
        client=unprivileged_client,
        cloud_init_data=cloud_init_data,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def bridge_attached_vmb(nodes, namespace, unprivileged_client, nad):
    name = "vmb"
    networks = {nad.name: nad.name}
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["bootcmd"] = nmcli_add_con_cmds("eth1", "192.168.0.2")

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name),
        networks=networks,
        interfaces=sorted(networks.keys()),
        node_selector=nodes[1].name,
        client=unprivileged_client,
        cloud_init_data=cloud_init_data,
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


@pytest.mark.polarion("CNV-2685")
def test_connectivity_over_linux_bridge_large_mtu(
    skip_if_no_multinic_nodes,
    skip_when_one_node,
    namespace,
    bridge,
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
        dst_ip=get_vmi_ip_v4_by_name(vmi=running_bridge_attached_vmib, name=nad.name),
        packetsize=nad.mtu - ip_header - icmp_header,
    )
