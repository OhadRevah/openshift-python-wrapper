"""
SR-IOV Tests
"""

import logging
import shlex

import pytest
from ocp_resources.utils import TimeoutSampler

from utilities.constants import SRIOV
from utilities.hco import (
    replace_backup_hco_cr_modification,
    restore_hco_cr_modification,
)
from utilities.infra import run_ssh_commands
from utilities.network import cloud_init_network_data, network_nad, sriov_network_dict
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    restart_guest_agent,
    running_vm,
)


LOGGER = logging.getLogger(__name__)
VM_SRIOV_IFACE_NAME = "sriov1"


def sriov_vm(
    _index_number,
    unprivileged_client,
    name,
    namespace,
    ip_config,
    sriov_network,
    worker=None,
):
    network_data_data = {
        "ethernets": {
            "eth1": {
                "addresses": [ip_config],
                "set-name": VM_SRIOV_IFACE_NAME,
            }
        }
    }
    networks = sriov_network_dict(namespace=namespace, network=sriov_network)
    cloud_init_data = cloud_init_network_data(data=network_data_data)

    vm_kwargs = {
        "namespace": namespace.name,
        "name": name,
        "body": fedora_vm_body(name=name),
        "networks": networks,
        "interfaces": networks.keys(),
        "cloud_init_data": cloud_init_data,
        "client": unprivileged_client,
        "interfaces_types": {name: SRIOV for name in networks.keys()},
    }

    if worker:
        vm_kwargs["node_selector"] = worker.name
    with VirtualMachineForTests(**vm_kwargs) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="class")
def skip_insufficient_sriov_workers(sriov_workers):
    """
    This function will make sure at least 2 worker nodes has SR-IOV capability
    else tests will be skip.
    """
    if len(sriov_workers) < 2:
        pytest.skip(msg="Test requires at least 2 SR-IOV worker nodes")


@pytest.fixture(scope="class")
def sriov_workers_node1(sriov_workers):
    """
    Get first worker nodes with SR-IOV capabilities
    """
    return sriov_workers[0]


@pytest.fixture(scope="class")
def sriov_workers_node2(sriov_workers):
    """
    Get second worker nodes with SR-IOV capabilities
    """
    return sriov_workers[1]


@pytest.fixture(scope="class")
def sriov_network(sriov_node_policy, namespace, sriov_namespace):
    """
    Create a SR-IOV network linked to SR-IOV policy.
    """
    with network_nad(
        nad_type=SRIOV,
        nad_name="sriov-test-network",
        sriov_resource_name=sriov_node_policy.resource_name,
        namespace=sriov_namespace,
        sriov_network_namespace=namespace.name,
    ) as sriov_network:
        yield sriov_network


@pytest.fixture(scope="class")
def sriov_network_vlan(sriov_node_policy, namespace, sriov_namespace, vlan_tag_id):
    """
    Create a SR-IOV VLAN network linked to SR-IOV policy.
    """
    with network_nad(
        nad_type=SRIOV,
        nad_name="sriov-test-network-vlan",
        sriov_resource_name=sriov_node_policy.resource_name,
        namespace=sriov_namespace,
        sriov_network_namespace=namespace.name,
        vlan=vlan_tag_id["1000"],
    ) as sriov_network:
        yield sriov_network


@pytest.fixture(scope="class")
def sriov_vm1(
    index_number, sriov_workers_node1, namespace, unprivileged_client, sriov_network
):
    yield from sriov_vm(
        _index_number=next(index_number),
        unprivileged_client=unprivileged_client,
        name="sriov-vm1",
        namespace=namespace,
        worker=sriov_workers_node1,
        ip_config="10.200.1.1/24",
        sriov_network=sriov_network,
    )


@pytest.fixture(scope="class")
def running_sriov_vm1(sriov_vm1):
    return running_vm(vm=sriov_vm1)


@pytest.fixture(scope="class")
def sriov_vm2(
    index_number, unprivileged_client, sriov_workers_node2, namespace, sriov_network
):
    yield from sriov_vm(
        _index_number=next(index_number),
        unprivileged_client=unprivileged_client,
        name="sriov-vm2",
        namespace=namespace,
        worker=sriov_workers_node2,
        ip_config="10.200.1.2/24",
        sriov_network=sriov_network,
    )


@pytest.fixture(scope="class")
def running_sriov_vm2(sriov_vm2):
    return running_vm(vm=sriov_vm2)


@pytest.fixture(scope="class")
def sriov_vm3(
    index_number,
    sriov_workers_node1,
    namespace,
    unprivileged_client,
    sriov_network_vlan,
):
    yield from sriov_vm(
        _index_number=next(index_number),
        unprivileged_client=unprivileged_client,
        name="sriov-vm3",
        namespace=namespace,
        worker=sriov_workers_node1,
        ip_config="10.200.3.1/24",
        sriov_network=sriov_network_vlan,
    )


@pytest.fixture(scope="class")
def running_sriov_vm3(sriov_vm3):
    return running_vm(vm=sriov_vm3)


@pytest.fixture(scope="class")
def sriov_vm4(
    index_number,
    sriov_workers_node2,
    namespace,
    unprivileged_client,
    sriov_network_vlan,
):
    yield from sriov_vm(
        _index_number=next(index_number),
        unprivileged_client=unprivileged_client,
        name="sriov-vm4",
        namespace=namespace,
        worker=sriov_workers_node2,
        ip_config="10.200.3.2/24",
        sriov_network=sriov_network_vlan,
    )


@pytest.fixture(scope="class")
def running_sriov_vm4(sriov_vm4):
    return running_vm(vm=sriov_vm4)


@pytest.fixture(scope="class")
def vm4_interfaces(running_sriov_vm4):
    sampler = TimeoutSampler(
        wait_timeout=60, sleep=10, func=lambda: running_sriov_vm4.vmi.interfaces
    )
    for sample in sampler:
        if len(sample) == 2:
            # 2 is used to make sure that number of interfaces before reboot are 2 then proceed.
            # Later this will be compared with number of interfaces after reboot.
            return sample
        restart_guest_agent(vm=running_sriov_vm4)


@pytest.fixture(params=list(range(1, 6)))
def rebooted_sriov_vm4(request, running_sriov_vm4):
    LOGGER.info(f"Reboot number {request.param}")
    # Reboot the VM
    run_ssh_commands(
        host=running_sriov_vm4.ssh_exec, commands=[shlex.split("sudo reboot")]
    )
    # Make sure the VM is up, otherwise we will get an old VM interfaces data.
    running_sriov_vm4.ssh_exec.executor().is_connective(tcp_timeout=60)
    restart_guest_agent(vm=running_sriov_vm4)
    return running_sriov_vm4


def get_vm_sriov_network_mtu(vm):
    return int(
        run_ssh_commands(
            host=vm.ssh_exec,
            commands=[shlex.split(f"cat /sys/class/net/{VM_SRIOV_IFACE_NAME}/mtu")],
        )[0]
    )


def set_vm_sriov_network_mtu(vm, mtu):
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=[shlex.split(f"sudo ip link set {VM_SRIOV_IFACE_NAME} mtu {mtu}")],
    )
    LOGGER.info(f"wait for {vm.name} {VM_SRIOV_IFACE_NAME} mtu to be {mtu}")
    for sample in TimeoutSampler(
        wait_timeout=30, sleep=1, func=get_vm_sriov_network_mtu, vm=vm
    ):
        if sample == mtu:
            return


@pytest.fixture()
def sriov_network_mtu_9000(sriov_vm1, sriov_vm2, running_sriov_vm1, running_sriov_vm2):
    vms = (running_sriov_vm1, running_sriov_vm2)
    default_mtu = (
        get_vm_sriov_network_mtu(vm=running_sriov_vm1),
        get_vm_sriov_network_mtu(vm=running_sriov_vm2),
    )
    for vm in vms:
        set_vm_sriov_network_mtu(vm=vm, mtu=9000)
    yield
    for vm, mtu in zip(vms, default_mtu):
        set_vm_sriov_network_mtu(vm=vm, mtu=mtu)


@pytest.fixture(scope="class")
def sriov_vm_migrate(index_number, unprivileged_client, namespace, sriov_network):
    yield from sriov_vm(
        _index_number=next(index_number),
        unprivileged_client=unprivileged_client,
        name="sriov-vm-migrate",
        namespace=namespace,
        ip_config="10.200.1.3/24",
        sriov_network=sriov_network,
    )


@pytest.fixture(scope="class")
def running_sriov_vm_migrate(sriov_vm_migrate):
    return running_vm(vm=sriov_vm_migrate)


@pytest.fixture(scope="class")
def enabled_sriovlivemigration_fg(
    hyperconverged_resource_scope_class, admin_client, hco_namespace
):
    # TODO : Remove this fixture in 4.9.0 .SRIOVLiveMigration will be by default enabled there.
    #  https://issues.redhat.com/browse/CNV-12276
    backup_data = replace_backup_hco_cr_modification(
        rpatch={"spec": {"featureGates": {"sriovLiveMigration": True}}},
        admin_client=admin_client,
        hco_namespace=hco_namespace,
    )
    yield
    restore_hco_cr_modification(
        admin_client=admin_client, hco_namespace=hco_namespace, backup_data=backup_data
    )
