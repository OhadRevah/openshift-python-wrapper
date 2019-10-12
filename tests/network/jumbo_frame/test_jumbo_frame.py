"""
VM to VM connectivity with  custom MTU (jumbo frame)
"""
import re

import pytest
from tests.network.utils import (
    assert_ping_successful,
    get_vmi_ip_v4_by_name,
    linux_bridge_nad,
    nmcli_add_con_cmds,
)
from utilities.infra import create_ns
from utilities.network import LinuxBridgeNodeNetworkConfigurationPolicy
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


MTU_SIZE = 9000
BR1TEST = "br1test"


class BridgedMtuFedoraVirtualMachine(VirtualMachineForTests):
    def __init__(
        self,
        name,
        namespace,
        client=None,
        interfaces=None,
        networks=None,
        node_selector=None,
        cloud_init_data=None,
    ):
        super().__init__(
            name=name,
            namespace=namespace,
            client=client,
            interfaces=interfaces,
            networks=networks,
            node_selector=node_selector,
            cloud_init_data=cloud_init_data,
        )

    def _to_dict(self):
        self.body = fedora_vm_body(self.name)
        res = super()._to_dict()
        return res


@pytest.fixture(scope="module", autouse=True)
def module_namespace(unprivileged_client):
    yield from create_ns(client=unprivileged_client, name="jumbo-frame-test")


@pytest.fixture(scope="module", autouse=True)
def br1test_nad(module_namespace):
    with linux_bridge_nad(
        namespace=module_namespace,
        name=BR1TEST,
        bridge=BR1TEST,
        tuning=True,
        mtu=MTU_SIZE,
    ) as nad:
        yield nad


@pytest.fixture(scope="module", autouse=True)
def bridge_on_all_nodes(network_utility_pods, nodes_active_nics):
    ports = [nodes_active_nics[network_utility_pods[0].node.name][1]]
    with LinuxBridgeNodeNetworkConfigurationPolicy(
        name="jumbo-frame",
        bridge_name=BR1TEST,
        worker_pods=network_utility_pods,
        ports=ports,
        mtu=MTU_SIZE,
    ) as br:
        yield br


@pytest.fixture(scope="module")
def bridge_attached_vma(nodes, module_namespace, unprivileged_client):
    networks = {BR1TEST: BR1TEST}
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["bootcmd"] = nmcli_add_con_cmds("eth1", "192.168.0.1")

    with BridgedMtuFedoraVirtualMachine(
        namespace=module_namespace.name,
        name="vma",
        networks=networks,
        interfaces=sorted(networks.keys()),
        node_selector=nodes[0].name,
        client=unprivileged_client,
        cloud_init_data=cloud_init_data,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def bridge_attached_vmb(nodes, module_namespace, unprivileged_client):
    networks = {BR1TEST: BR1TEST}
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["bootcmd"] = nmcli_add_con_cmds("eth1", "192.168.0.2")

    with BridgedMtuFedoraVirtualMachine(
        namespace=module_namespace.name,
        name="vmb",
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


# TODO: this should be handled by bridge CNI, This fixture should be removed once it's fixed
# https://github.com/containernetworking/plugins/issues/352
@pytest.fixture(scope="module")
def fixed_veth_mtu_on_host(
    network_utility_pods, running_bridge_attached_vmia, running_bridge_attached_vmib
):
    for vmi in (running_bridge_attached_vmia, running_bridge_attached_vmib):
        pod = [pod for pod in network_utility_pods if vmi.node.name == pod.node.name][0]
        ip_link_out = pod.execute(
            ["bash", "-c", "--", f"ip -o link show type veth | grep {BR1TEST}"]
        )
        for line in ip_link_out.split("\n"):
            veth_match = re.findall(r"veth.*@", line)
            if veth_match:
                veth = veth_match[0].strip("@")
                pod.execute(["ip", "link", "set", veth, "mtu", MTU_SIZE])


@pytest.mark.polarion("CNV-2685")
def test_connectivity_over_linux_bridge_large_mtu(
    skip_if_no_multinic_nodes,
    skip_when_one_node,
    module_namespace,
    bridge_attached_vma,
    bridge_attached_vmb,
    fixed_veth_mtu_on_host,
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
        dst_ip=get_vmi_ip_v4_by_name(vmi=running_bridge_attached_vmib, name=BR1TEST),
        packetsize=MTU_SIZE - ip_header - icmp_header,
    )
