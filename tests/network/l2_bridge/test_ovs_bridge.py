import shlex
from collections import OrderedDict

import pytest

from utilities.infra import run_ssh_commands
from utilities.network import (
    OVS,
    assert_ping_successful,
    compose_cloud_init_data_dict,
    network_nad,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


OVS_BR = "test-ovs-br"
SEC_IFACE_SUBNET = "10.0.200"
DST_IP_ADDR = SEC_IFACE_SUBNET + ".2"


@pytest.fixture()
def node1_executor(worker_node1, workers_ssh_executors):
    return workers_ssh_executors[worker_node1.name]


@pytest.fixture()
def ovs_bridge_on_worker1(node1_executor):
    cmd = "sudo ovs-vsctl"
    run_ssh_commands(
        host=node1_executor, commands=[shlex.split(f"{cmd} add-br {OVS_BR}")]
    )
    yield OVS_BR
    run_ssh_commands(
        host=node1_executor, commands=[shlex.split(f"{cmd} del-br {OVS_BR}")]
    )


@pytest.fixture()
def ovs_bridge_nad(namespace, ovs_bridge_on_worker1):
    with network_nad(
        namespace=namespace,
        nad_type=OVS,
        nad_name="ovs-test-nad",
        interface_name=ovs_bridge_on_worker1,
    ) as nad:
        yield nad


@pytest.fixture()
def vma_with_ovs_based_l2(
    unprivileged_client,
    namespace,
    worker_node1,
    ovs_bridge_on_worker1,
    ovs_bridge_nad,
):
    vm_name = "vm-a-ovs-sec-iface"
    networks = OrderedDict()
    networks[ovs_bridge_nad.name] = ovs_bridge_nad.name
    network_data = {
        "ethernets": {
            "eth1": {"addresses": [f"{SEC_IFACE_SUBNET}.1/24"]},
        }
    }
    cloud_init_data = compose_cloud_init_data_dict(network_data=network_data)

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=vm_name,
        body=fedora_vm_body(name=vm_name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=worker_node1.name,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture()
def running_vma_with_ovs_based_l2(vma_with_ovs_based_l2):
    return running_vm(vm=vma_with_ovs_based_l2)


@pytest.fixture()
def vmb_with_ovs_based_l2(
    unprivileged_client,
    namespace,
    worker_node1,
    ovs_bridge_on_worker1,
    ovs_bridge_nad,
):
    vm_name = "vm-b-ovs-sec-iface"
    networks = OrderedDict()
    networks[ovs_bridge_nad.name] = ovs_bridge_nad.name
    network_data = {
        "ethernets": {
            "eth1": {"addresses": [f"{DST_IP_ADDR}/24"]},
        }
    }
    cloud_init_data = compose_cloud_init_data_dict(network_data=network_data)

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=vm_name,
        body=fedora_vm_body(name=vm_name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=worker_node1.name,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture()
def running_vmb_with_ovs_based_l2(vmb_with_ovs_based_l2):
    return running_vm(vm=vmb_with_ovs_based_l2)


@pytest.mark.polarion("CNV-5636")
def test_ovs_bridge_sanity(
    skip_if_ovn_cluster,
    hyperconverged_ovs_annotations_enabled,
    vma_with_ovs_based_l2,
    vmb_with_ovs_based_l2,
    running_vma_with_ovs_based_l2,
    running_vmb_with_ovs_based_l2,
):
    assert_ping_successful(src_vm=running_vma_with_ovs_based_l2, dst_ip=DST_IP_ADDR)