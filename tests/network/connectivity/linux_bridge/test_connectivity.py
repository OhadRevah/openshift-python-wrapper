"""
VM to VM connectivity
"""

import pytest
from pytest_testconfig import config as py_config

from resources.namespace import Namespace
from tests.network.connectivity.utils import run_test_guest_performance
from tests.network.utils import (
    bridge_nad,
    run_test_connectivity,
    get_vmi_ip_v4_by_name,
    VXLANTunnel,
    Bridge,
    nmcli_add_con_cmds,
)
from tests.utils import FedoraVirtualMachine, wait_for_vm_interfaces

BR1TEST = "br1test"
BR1BOND = "br1bond"
BR1VLAN100 = "br1vlan100"
BR1VLAN200 = "br1vlan200"
BR1VLAN300 = "br1vlan300"


class BridgedFedoraVirtualMachine(FedoraVirtualMachine):
    def __init__(
        self,
        name,
        namespace,
        client=None,
        interfaces=None,
        networks=None,
        node_selector=None,
        bootcmds=None,
    ):
        super().__init__(
            name=name,
            namespace=namespace,
            client=client,
            interfaces=interfaces,
            networks=networks,
            node_selector=node_selector,
        )
        self.bootcmds = bootcmds

    def _cloud_init_user_data(self):
        data = super()._cloud_init_user_data()
        data["bootcmd"] = self.bootcmds
        return data


@pytest.fixture(scope="module", autouse=True)
def module_namespace():
    with Namespace(name="linux-bridge-connectivity") as ns:
        yield ns


@pytest.fixture(scope="module", autouse=True)
def br1test_nad(module_namespace):
    with bridge_nad(namespace=module_namespace, name=BR1TEST, bridge=BR1TEST) as nad:
        yield nad


@pytest.fixture(scope="module", autouse=True)
def brbond_nad(module_namespace):
    with bridge_nad(namespace=module_namespace, name=BR1BOND, bridge=BR1BOND) as nad:
        yield nad


@pytest.fixture(scope="module", autouse=True)
def br1vlan100_nad(module_namespace):
    with bridge_nad(
        namespace=module_namespace, name=BR1VLAN100, bridge=BR1TEST, vlan=100
    ) as nad:
        yield nad


@pytest.fixture(scope="module", autouse=True)
def br1vlan200_nad(module_namespace):
    with bridge_nad(
        namespace=module_namespace, name=BR1VLAN200, bridge=BR1TEST, vlan=200
    ) as nad:
        yield nad


@pytest.fixture(scope="module", autouse=True)
def br1vlan300_nad(module_namespace):
    with bridge_nad(
        namespace=module_namespace, name=BR1VLAN300, bridge=BR1TEST, vlan=300
    ) as nad:
        yield nad


@pytest.fixture(scope="module", autouse=True)
def bridge_on_all_nodes(network_utility_pods, nodes_active_nics, multi_nics_nodes):

    master_index = 1 if multi_nics_nodes else None

    with Bridge(
        name=BR1TEST,
        worker_pods=network_utility_pods,
        master_index=master_index,
        vlan_filtering=True,
        nodes_nics=nodes_active_nics,
    ) as br:
        if not multi_nics_nodes:
            with VXLANTunnel(
                name="vxlan_lb_99",
                worker_pods=network_utility_pods,
                vxlan_id=99,
                master_bridge=br.name,
                nodes_nics=nodes_active_nics,
            ):
                yield br
        else:
            yield br


@pytest.fixture(scope="module")
def bridge_attached_vma(nodes, bond_supported, module_namespace):
    networks = {BR1TEST: BR1TEST, BR1VLAN100: BR1VLAN100, BR1VLAN200: BR1VLAN200}
    bootcmds = []
    bootcmds.extend(nmcli_add_con_cmds("eth1", "192.168.0.1"))
    bootcmds.extend(nmcli_add_con_cmds("eth2", "192.168.1.1"))
    bootcmds.extend(nmcli_add_con_cmds("eth3", "192.168.2.1"))
    if bond_supported:
        bootcmds.extend(nmcli_add_con_cmds("eth4", "192.168.3.1"))
        networks[BR1BOND] = BR1BOND

    with BridgedFedoraVirtualMachine(
        namespace=module_namespace.name,
        name="vma",
        networks=networks,
        interfaces=sorted(networks.keys()),
        node_selector=nodes[0].name,
        bootcmds=bootcmds,
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture(scope="module")
def bridge_attached_vmb(nodes, bond_supported, module_namespace):
    networks = {BR1TEST: BR1TEST, BR1VLAN100: BR1VLAN100, BR1VLAN300: BR1VLAN300}
    bootcmds = []
    bootcmds.extend(nmcli_add_con_cmds("eth1", "192.168.0.2"))
    bootcmds.extend(nmcli_add_con_cmds("eth2", "192.168.1.2"))
    bootcmds.extend(nmcli_add_con_cmds("eth3", "192.168.2.2"))
    if bond_supported:
        bootcmds.extend(nmcli_add_con_cmds("eth4", "192.168.3.2"))
        networks[BR1BOND] = BR1BOND

    with BridgedFedoraVirtualMachine(
        namespace=module_namespace.name,
        name="vmb",
        networks=networks,
        interfaces=sorted(networks.keys()),
        node_selector=nodes[1].name,
        bootcmds=bootcmds,
    ) as vm:
        vm.start()
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
        pytest.param("default", marks=(pytest.mark.polarion("CNV-2350"))),
        pytest.param(BR1TEST, marks=(pytest.mark.polarion("CNV-2080"))),
        pytest.param(
            BR1VLAN100,
            marks=(
                pytest.mark.polarion("CNV-2072"),
                pytest.mark.skipif(
                    py_config["bare_metal_cluster"],
                    reason="Missing VLAN config on the switch [Ticket PNT0584216]",
                ),
            ),
        ),
        pytest.param(BR1BOND, marks=(pytest.mark.polarion("CNV-2141"))),
        pytest.param(BR1VLAN300, marks=(pytest.mark.polarion("CNV-2075"))),
    ],
    ids=[
        "Connectivity_between_VM_to_VM_over_POD_network_make_sure_it_works_while_L2_networks_exists",
        "Connectivity_between_VM_to_VM_over_L2_Linux_bridge_network",
        "Connectivity_between_VM_to_VM_over_L2_Linux_bridge_VLAN_network",
        "Connectivity_between_VM_to_VM_over_L2_Linux_bridge_on_BOND_network",
        "Negative_No_connectivity_between_VM_to_VM_L2_Linux_bridge_different_VLANs",
    ],
)
def test_connectivity_over_linux_bridge(
    skip_when_one_node,
    bridge,
    module_namespace,
    attach_linux_bridge_to_bond,
    bond_supported,
    bridge_attached_vma,
    bridge_attached_vmb,
    running_bridge_attached_vmia,
    running_bridge_attached_vmib,
):
    """
    Check connectivity
    """
    if bridge == BR1BOND:
        if not bond_supported:
            pytest.skip(msg="No BOND support")

    if bridge in (BR1VLAN100, BR1VLAN300) and py_config["bare_metal_cluster"]:
        # TODO: Remove when trunk is configured on the switches
        # https://redhat.service-now.com/surl.do?n=PNT0584216
        pytest.skip(msg="Running on BM, no trunk on switches yet!!")

    # Using masquerade we can just ping vmb pods ip
    vmib_bridge_inteface = next(
        i for i in running_bridge_attached_vmib.interfaces if i["name"] == bridge
    )
    if bridge == "default" and "masquerade" in vmib_bridge_inteface:
        vmb_ip = running_bridge_attached_vmib.virt_launcher_pod.instance.status.podIP
    else:
        vmb_ip = get_vmi_ip_v4_by_name(vmi=running_bridge_attached_vmib, name=bridge)

    positive = bridge != BR1VLAN300
    run_test_connectivity(src_vm=bridge_attached_vma, dst_ip=vmb_ip, positive=positive)


@pytest.mark.skipif(not py_config["bare_metal_cluster"], reason="virtualized cluster")
@pytest.mark.xfail(reason="Slow performance on BM, need investigation")
@pytest.mark.polarion("CNV-2335")
def test_guest_performance_over_linux_bridge(
    skip_when_one_node,
    module_namespace,
    bridge_attached_vma,
    bridge_attached_vmb,
    running_bridge_attached_vmia,
    running_bridge_attached_vmib,
):
    """
    In-guest performance bandwidth passthrough over Linux bridge
    """
    expected_res = py_config["test_guest_performance"]["bandwidth"]
    bits_per_second = run_test_guest_performance(
        server_vm=bridge_attached_vma,
        client_vm=bridge_attached_vmb,
        listen_ip=get_vmi_ip_v4_by_name(vmi=running_bridge_attached_vmia, name=BR1TEST),
    )
    assert bits_per_second >= expected_res
