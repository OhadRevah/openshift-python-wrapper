"""
VM to VM connectivity with  custom MTU (jumbo frame)
"""

import pytest
from tests.network.utils import (
    assert_ping_successful,
    get_vmi_ip_v4_by_name,
    linux_bridge_nad,
    nmcli_add_con_cmds,
)
from utilities.network import LinuxBridgeNodeNetworkConfigurationPolicy
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


@pytest.fixture(scope="module")
def br1test_nad(namespace):
    with linux_bridge_nad(
        namespace=namespace,
        name="br1test-nad",
        bridge="br1test",
        tuning=True,
        mtu=9000,
    ) as nad:
        yield nad


@pytest.fixture(scope="module", autouse=True)
def bridge_on_all_nodes(network_utility_pods, nodes_active_nics, br1test_nad):
    ports = [nodes_active_nics[network_utility_pods[0].node.name][1]]

    with LinuxBridgeNodeNetworkConfigurationPolicy(
        name="jumbo-frame",
        bridge_name=br1test_nad.bridge_name,
        worker_pods=network_utility_pods,
        ports=ports,
        mtu=br1test_nad.mtu,
    ) as br:
        yield br


@pytest.fixture(scope="module")
def bridge_attached_vma(nodes, namespace, unprivileged_client, br1test_nad):
    name = "vma"
    networks = {br1test_nad.name: br1test_nad.name}
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
def bridge_attached_vmb(nodes, namespace, unprivileged_client, br1test_nad):
    name = "vmb"
    networks = {br1test_nad.name: br1test_nad.name}
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
    br1test_nad,
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
            vmi=running_bridge_attached_vmib, name=br1test_nad.name
        ),
        packetsize=br1test_nad.mtu - ip_header - icmp_header,
    )
