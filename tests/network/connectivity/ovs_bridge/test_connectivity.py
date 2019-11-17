"""
VM to VM connectivity
"""

import pytest
from pytest_testconfig import config as py_config
from tests.network.connectivity.utils import run_test_guest_performance
from tests.network.utils import (
    assert_no_ping,
    assert_ping_successful,
    get_vmi_ip_v4_by_name,
    nmcli_add_con_cmds,
    ovs_bridge_nad,
)
from utilities.network import OvsBridgeNodeNetworkConfigurationPolicy
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


BR1TEST = "br1test"
BR1BOND = "br1bond"
BR1VLAN100 = "br1vlan100"
BR1VLAN200 = "br1vlan200"
BR1VLAN300 = "br1vlan300"


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


class BridgedFedoraVirtualMachine(VirtualMachineForTests):
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


@pytest.fixture(scope="module")
def attach_ovs_bridge_to_bond(bond1, network_utility_pods):
    """
    Create bridge and attach the BOND to it
    """
    if bond1:
        bond_bridge = "br1bond"
        with OvsBridgeNodeNetworkConfigurationPolicy(
            name="bridge-to-bond",
            bridge_name=bond_bridge,
            worker_pods=network_utility_pods,
            ports=[bond1],
        ) as br:
            yield br
    else:
        yield


@pytest.fixture(scope="module", autouse=True)
def br1test_nad(namespace, ovs_bridge_on_all_nodes):
    with ovs_bridge_nad(
        namespace=namespace, name=BR1TEST, bridge=ovs_bridge_on_all_nodes.bridge_name
    ) as nad:
        yield nad


@pytest.fixture(scope="module", autouse=True)
def brbond_nad(namespace, ovs_bridge_on_all_nodes):
    with ovs_bridge_nad(
        namespace=namespace, name=BR1BOND, bridge=ovs_bridge_on_all_nodes.bridge_name
    ) as nad:
        yield nad


@pytest.fixture(scope="module", autouse=True)
def br1vlan100_nad(namespace, ovs_bridge_on_all_nodes):
    with ovs_bridge_nad(
        namespace=namespace,
        name=BR1VLAN100,
        bridge=ovs_bridge_on_all_nodes.bridge_name,
        vlan=100,
    ) as nad:
        yield nad


@pytest.fixture(scope="module", autouse=True)
def br1vlan200_nad(namespace, ovs_bridge_on_all_nodes):
    with ovs_bridge_nad(
        namespace=namespace,
        name=BR1VLAN200,
        bridge=ovs_bridge_on_all_nodes.bridge_name,
        vlan=200,
    ) as nad:
        yield nad


@pytest.fixture(scope="module", autouse=True)
def br1vlan300_nad(namespace, ovs_bridge_on_all_nodes):
    with ovs_bridge_nad(
        namespace=namespace,
        name=BR1VLAN300,
        bridge=ovs_bridge_on_all_nodes.bridge_name,
        vlan=300,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def bridge_attached_vma(nodes, bond_supported, namespace, unprivileged_client):
    networks = {BR1TEST: BR1TEST, BR1VLAN100: BR1VLAN100, BR1VLAN200: BR1VLAN200}
    bootcmds = []
    bootcmds.extend(nmcli_add_con_cmds("eth1", "192.168.0.1"))
    bootcmds.extend(nmcli_add_con_cmds("eth2", "192.168.1.1"))
    bootcmds.extend(nmcli_add_con_cmds("eth3", "192.168.2.1"))
    if bond_supported:
        bootcmds.extend(nmcli_add_con_cmds("eth4", "192.168.3.1"))
        networks[BR1BOND] = BR1BOND

    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["bootcmd"] = bootcmds

    with BridgedFedoraVirtualMachine(
        namespace=namespace.name,
        name="vma",
        networks=networks,
        interfaces=sorted(networks.keys()),
        node_selector=nodes[0].name,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def bridge_attached_vmb(nodes, bond_supported, namespace, unprivileged_client):
    networks = {BR1TEST: BR1TEST, BR1VLAN100: BR1VLAN100, BR1VLAN300: BR1VLAN300}
    bootcmds = []
    bootcmds.extend(nmcli_add_con_cmds("eth1", "192.168.0.2"))
    bootcmds.extend(nmcli_add_con_cmds("eth2", "192.168.1.2"))
    bootcmds.extend(nmcli_add_con_cmds("eth3", "192.168.2.2"))
    if bond_supported:
        bootcmds.extend(nmcli_add_con_cmds("eth4", "192.168.3.2"))
        networks[BR1BOND] = BR1BOND

    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["bootcmd"] = bootcmds

    with BridgedFedoraVirtualMachine(
        namespace=namespace.name,
        name="vmb",
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
            marks=(pytest.mark.polarion("CNV-2899")),
            id="Connectivity_between_VM_to_VM_over_POD_network_make_sure_it_works_while_L2_networks_exists",
        ),
        pytest.param(
            BR1TEST,
            marks=(pytest.mark.polarion("CNV-2900")),
            id="Connectivity_between_VM_to_VM_over_L2_ovs_bridge_network",
        ),
    ],
)
def test_connectivity_over_ovs_bridge(
    bridge,
    skip_when_one_node,
    namespace,
    attach_ovs_bridge_to_bond,
    bridge_attached_vma,
    bridge_attached_vmb,
    running_bridge_attached_vmia,
    running_bridge_attached_vmib,
):
    assert_ping_successful(
        src_vm=running_bridge_attached_vmia,
        dst_ip=_masquerade_vmib_ip(running_bridge_attached_vmib, bridge),
    )


@pytest.mark.polarion("CNV-2902")
def test_connectivity_bond_over_ovs_bridge(
    skip_when_one_node,
    namespace,
    attach_ovs_bridge_to_bond,
    bond_supported,
    bridge_attached_vma,
    bridge_attached_vmb,
    running_bridge_attached_vmia,
    running_bridge_attached_vmib,
):
    if not bond_supported:
        pytest.skip(msg="No BOND support")

    assert_ping_successful(
        src_vm=running_bridge_attached_vmia,
        dst_ip=get_vmi_ip_v4_by_name(vmi=running_bridge_attached_vmib, name=BR1BOND),
    )


@pytest.mark.skipif(
    py_config["bare_metal_cluster"], reason="Running on BM, no trunk on switches yet!!"
)
@pytest.mark.polarion("CNV-2901")
def test_connectivity_positive_vlan_over_ovs_bridge(
    skip_when_one_node,
    namespace,
    attach_ovs_bridge_to_bond,
    bridge_attached_vma,
    bridge_attached_vmb,
    running_bridge_attached_vmia,
    running_bridge_attached_vmib,
):
    assert_ping_successful(
        src_vm=running_bridge_attached_vmia,
        dst_ip=get_vmi_ip_v4_by_name(vmi=running_bridge_attached_vmib, name=BR1VLAN100),
    )


@pytest.mark.skipif(
    py_config["bare_metal_cluster"], reason="Running on BM, no trunk on switches yet!!"
)
@pytest.mark.polarion("CNV-2903")
def test_connectivity_negative_vlan_over_ovs_bridge(
    skip_when_one_node,
    namespace,
    attach_ovs_bridge_to_bond,
    bridge_attached_vma,
    bridge_attached_vmb,
    running_bridge_attached_vmia,
    running_bridge_attached_vmib,
):
    assert_no_ping(
        src_vm=running_bridge_attached_vmia,
        dst_ip=get_vmi_ip_v4_by_name(vmi=running_bridge_attached_vmib, name=BR1VLAN300),
    )


@pytest.mark.skipif(not py_config["bare_metal_cluster"], reason="virtualized cluster")
@pytest.mark.xfail(reason="Slow performance on BM, need investigation")
@pytest.mark.polarion("CNV-2335")
def test_guest_performance_over_ovs_bridge(
    skip_when_one_node,
    namespace,
    attach_ovs_bridge_to_bond,
    bridge_attached_vma,
    bridge_attached_vmb,
    running_bridge_attached_vmia,
    running_bridge_attached_vmib,
):
    """
    In-guest performance bandwidth passthrough over OVS bridge
    """
    expected_res = py_config["test_guest_performance"]["bandwidth"]
    bits_per_second = run_test_guest_performance(
        server_vm=bridge_attached_vma,
        client_vm=bridge_attached_vmb,
        listen_ip=get_vmi_ip_v4_by_name(vmi=running_bridge_attached_vmia, name=BR1TEST),
    )
    assert bits_per_second >= expected_res
