"""
VM to VM connectivity
"""
from collections import OrderedDict

import pytest

from utilities.network import (
    OVS,
    assert_ping_successful,
    cloud_init_network_data,
    get_vmi_ip_v4_by_name,
    network_nad,
)
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
def rhel7_nad(rhel7_ovs_bridge, namespace):
    with network_nad(
        namespace=namespace,
        nad_type=OVS,
        nad_name="br1test-nad",
        interface_name=rhel7_ovs_bridge,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def rhel7_bridge_attached_vma(worker_node1, namespace, unprivileged_client, rhel7_nad):
    name = "vma"
    networks = OrderedDict()
    networks[rhel7_nad.name] = rhel7_nad.name
    network_data_data = {"ethernets": {"eth1": {"addresses": ["10.200.0.1/24"]}}}
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data.update(cloud_init_network_data(data=network_data_data))

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
def rhel7_bridge_attached_vmb(worker_node2, namespace, unprivileged_client, rhel7_nad):
    name = "vmb"
    networks = OrderedDict()
    networks[rhel7_nad.name] = rhel7_nad.name
    network_data_data = {"ethernets": {"eth1": {"addresses": ["10.200.0.2/24"]}}}
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data.update(cloud_init_network_data(data=network_data_data))

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
def rhel7_running_bridge_attached_vmia(rhel7_bridge_attached_vma):
    vmi = rhel7_bridge_attached_vma.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    return vmi


@pytest.fixture(scope="class")
def rhel7_running_bridge_attached_vmib(rhel7_bridge_attached_vmb):
    vmi = rhel7_bridge_attached_vmb.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    return vmi


@pytest.mark.polarion("CNV-3691")
def test_l2_bridge_connectivity(
    skip_no_rhel7_workers,
    rhel7_workers,
    skip_when_one_node,
    namespace,
    rhel7_nad,
    rhel7_bridge_attached_vma,
    rhel7_bridge_attached_vmb,
    rhel7_running_bridge_attached_vmia,
    rhel7_running_bridge_attached_vmib,
):
    assert_ping_successful(
        src_vm=rhel7_running_bridge_attached_vmia,
        dst_ip=_masquerade_vmib_ip(rhel7_running_bridge_attached_vmib, rhel7_nad.name),
    )
