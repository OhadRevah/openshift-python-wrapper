"""
VM to VM connectivity
"""
from collections import OrderedDict

import pytest
import utilities.network
from tests.network.utils import assert_ping_successful, nmcli_add_con_cmds
from utilities.infra import BUG_STATUS_CLOSED
from utilities.network import bridge_nad, get_vmi_ip_v4_by_name
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
def nad(rhel7_ovs_bridge, namespace):
    with bridge_nad(
        namespace=namespace,
        nad_type=utilities.network.OVS,
        nad_name="br1test-nad",
        bridge_name=rhel7_ovs_bridge,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def bridge_attached_vma(schedulable_nodes, namespace, unprivileged_client, nad):
    name = "vma"
    networks = OrderedDict()
    networks[nad.name] = nad.name
    bootcmds = []
    bootcmds.extend(nmcli_add_con_cmds("eth1", "192.168.0.1"))
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["bootcmd"] = bootcmds

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=schedulable_nodes[2].name,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="class")
def bridge_attached_vmb(schedulable_nodes, namespace, unprivileged_client, nad):
    name = "vmb"
    networks = OrderedDict()
    networks[nad.name] = nad.name
    bootcmds = []
    bootcmds.extend(nmcli_add_con_cmds("eth1", "192.168.0.2"))
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


class TestConnectivity:
    @pytest.mark.parametrize(
        "bridge",
        [
            pytest.param(
                "default",
                marks=(
                    pytest.mark.polarion("CNV-3692"),
                    pytest.mark.bugzilla(
                        1787576,
                        skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED,
                    ),
                ),
                id="RHEL7-Connectivity_between_VM_to_VM_over_POD_network_make_sure_it_works_while_L2_networks_exists",
            ),
            pytest.param(
                "br1test-nad",
                marks=(pytest.mark.polarion("CNV-3691")),
                id="RHEL7-Connectivity_between_VM_to_VM_over_L2_bridge_network",
            ),
        ],
    )
    def test_bridge(
        self,
        bridge,
        skip_no_rhel7_workers,
        rhel7_workers,
        skip_when_one_node,
        namespace,
        bridge_attached_vma,
        bridge_attached_vmb,
        running_bridge_attached_vmia,
        running_bridge_attached_vmib,
    ):
        assert_ping_successful(
            src_vm=running_bridge_attached_vmia,
            dst_ip=_masquerade_vmib_ip(running_bridge_attached_vmib, bridge),
        )
