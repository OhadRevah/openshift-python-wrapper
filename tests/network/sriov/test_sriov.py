"""
SR-IOV Tests
"""

import logging
import shlex
from ipaddress import ip_interface

import pytest
from ocp_resources.namespace import Namespace
from ocp_resources.utils import TimeoutSampler
from pytest_testconfig import config as py_config

from tests.network.utils import assert_no_ping, run_test_guest_performance
from utilities.constants import SRIOV
from utilities.infra import run_ssh_commands
from utilities.network import (
    assert_ping_successful,
    cloud_init_network_data,
    get_vmi_ip_v4_by_name,
    network_nad,
    sriov_network_dict,
)
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
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
    worker,
    ip_config,
    sriov_network,
):
    sriov_mac = "02:00:b5:b5:b5:%02x" % _index_number
    network_data_data = {
        "ethernets": {
            "1": {
                "addresses": [ip_config],
                "match": {"macaddress": sriov_mac},
                "set-name": VM_SRIOV_IFACE_NAME,
            }
        }
    }
    networks = sriov_network_dict(namespace=namespace, network=sriov_network)
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data.update(cloud_init_network_data(data=network_data_data))

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=worker.name,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
        macs={sriov_network.name: sriov_mac},
        interfaces_types={name: SRIOV for name in networks.keys()},
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="class")
def sriov_namespace():
    return Namespace(name=py_config["sriov_namespace"])


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
        vlan=vlan_tag_id,
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
    index_number, sriov_workers_node2, namespace, unprivileged_client, sriov_network
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


def get_sriov1_mtu(vm):
    return int(
        run_ssh_commands(
            host=vm.ssh_exec,
            commands=[shlex.split(f"cat /sys/class/net/{VM_SRIOV_IFACE_NAME}/mtu")],
        )[0]
    )


def set_sriov1_mtu(vm, mtu):
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=[
            shlex.split(f"sudo ip link set {VM_SRIOV_IFACE_NAME} mtu {str(mtu)}")
        ],
    )
    LOGGER.info(f"wait for {vm.name} {VM_SRIOV_IFACE_NAME} mtu to be {mtu}")
    for sample in TimeoutSampler(wait_timeout=30, sleep=1, func=get_sriov1_mtu, vm=vm):
        if sample == mtu:
            return


@pytest.fixture()
def sriov1_mtu_9000(sriov_vm1, sriov_vm2, running_sriov_vm1, running_sriov_vm2):
    vms = (running_sriov_vm1, running_sriov_vm2)
    default_mtu = (
        get_sriov1_mtu(vm=running_sriov_vm1),
        get_sriov1_mtu(vm=running_sriov_vm2),
    )
    for vm in vms:
        set_sriov1_mtu(vm=vm, mtu=9000)
    yield
    for vm, mtu in zip(vms, default_mtu):
        set_sriov1_mtu(vm=vm, mtu=mtu)


@pytest.mark.usefixtures(
    "skip_when_no_sriov",
    "labeled_sriov_nodes",
    "skip_rhel7_workers",
    "skip_insufficient_sriov_workers",
)
class TestPingConnectivity:
    @pytest.mark.post_upgrade
    @pytest.mark.polarion("CNV-3963")
    def test_sriov_basic_connectivity(
        self,
        sriov_network,
        sriov_vm1,
        sriov_vm2,
        running_sriov_vm1,
        running_sriov_vm2,
    ):
        assert_ping_successful(
            src_vm=running_sriov_vm1,
            dst_ip=get_vmi_ip_v4_by_name(vm=running_sriov_vm2, name=sriov_network.name),
        )

    @pytest.mark.polarion("CNV-4505")
    def test_sriov_custom_mtu_connectivity(
        self,
        sriov_network,
        sriov_vm1,
        sriov_vm2,
        running_sriov_vm1,
        running_sriov_vm2,
        sriov1_mtu_9000,
    ):
        assert_ping_successful(
            src_vm=running_sriov_vm1,
            dst_ip=get_vmi_ip_v4_by_name(vm=running_sriov_vm2, name=sriov_network.name),
            packetsize=9000,
        )

    @pytest.mark.polarion("CNV-3958")
    def test_sriov_basic_connectivity_vlan(
        self,
        sriov_network_vlan,
        sriov_vm3,
        sriov_vm4,
        running_sriov_vm3,
        running_sriov_vm4,
    ):
        assert_ping_successful(
            src_vm=running_sriov_vm3,
            dst_ip=get_vmi_ip_v4_by_name(
                vm=running_sriov_vm4, name=sriov_network_vlan.name
            ),
        )

    @pytest.mark.polarion("CNV-4713")
    def test_sriov_no_connectivity_no_vlan_to_vlan(
        self,
        sriov_network_vlan,
        sriov_vm1,
        sriov_vm4,
        running_sriov_vm1,
        running_sriov_vm4,
    ):
        assert_no_ping(
            src_vm=running_sriov_vm1,
            dst_ip=get_vmi_ip_v4_by_name(
                vm=running_sriov_vm4, name=sriov_network_vlan.name
            ),
        )

    @pytest.mark.post_upgrade
    @pytest.mark.polarion("CNV-4768")
    def test_sriov_interfaces_post_reboot(
        self, sriov_vm4, running_sriov_vm4, vm4_interfaces, rebooted_sriov_vm4
    ):
        # Check only the second interface (SR-IOV interface).
        assert rebooted_sriov_vm4.vmi.interfaces[1] == vm4_interfaces[1]


@pytest.mark.polarion("CNV-4316")
def test_guest_performance(
    sriov_vm1,
    sriov_vm2,
    running_sriov_vm1,
    running_sriov_vm2,
):
    """
    In-guest performance bandwidth passthrough over SR-IOV interface.
    """
    expected_res = py_config["test_guest_performance"]["bandwidth"]
    bits_per_second = run_test_guest_performance(
        server_vm=sriov_vm1,
        client_vm=sriov_vm2,
        listen_ip=ip_interface(sriov_vm1.vmi.interfaces[1]["ipAddress"]).ip,
    )
    assert bits_per_second >= expected_res
