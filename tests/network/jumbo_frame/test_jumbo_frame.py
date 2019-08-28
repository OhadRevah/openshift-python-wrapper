"""
VM to VM connectivity with  custom MTU (jumbo frame)
"""
import re

import pytest

from tests.utils import create_ns
from tests.network.utils import (
    linux_bridge_nad,
    assert_ping_successful,
    get_vmi_ip_v4_by_name,
    nmcli_add_con_cmds,
)
from tests.utils import TestVirtualMachine, wait_for_vm_interfaces, Bridge

MTU_SIZE = 9000
BR1TEST = "br1test"


class BridgedMtuFedoraVirtualMachine(TestVirtualMachine):
    def __init__(
        self,
        name,
        namespace,
        client=None,
        interfaces=None,
        networks=None,
        node_selector=None,
        iface_ip=None,
    ):
        super().__init__(
            name=name,
            namespace=namespace,
            client=client,
            interfaces=interfaces,
            networks=networks,
            node_selector=node_selector,
        )
        self.iface_ip = iface_ip

    def _cloud_init_user_data(self):
        data = super()._cloud_init_user_data()
        data["bootcmd"] = nmcli_add_con_cmds("eth1", self.iface_ip)
        return data


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
    with Bridge(
        name=BR1TEST,
        worker_pods=network_utility_pods,
        master_index=1,
        nodes_nics=nodes_active_nics,
        mtu=MTU_SIZE,
    ) as br:
        yield br


@pytest.fixture(scope="module")
def bridge_attached_vma(nodes, module_namespace, unprivileged_client):
    networks = {BR1TEST: BR1TEST}
    with BridgedMtuFedoraVirtualMachine(
        namespace=module_namespace.name,
        name="vma",
        networks=networks,
        interfaces=sorted(networks.keys()),
        node_selector=nodes[0].name,
        iface_ip="192.168.0.1",
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.fixture(scope="module")
def bridge_attached_vmb(nodes, module_namespace, unprivileged_client):
    networks = {BR1TEST: BR1TEST}
    with BridgedMtuFedoraVirtualMachine(
        namespace=module_namespace.name,
        name="vmb",
        networks=networks,
        interfaces=sorted(networks.keys()),
        node_selector=nodes[1].name,
        iface_ip="192.168.0.2",
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
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
        mtu=MTU_SIZE - ip_header - icmp_header,
    )
