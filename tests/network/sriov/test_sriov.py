"""
Sriov Tests
"""
import pytest
from pytest_testconfig import config as py_config
from resources.sriov_network import SriovNetwork
from tests.network.utils import assert_ping_successful, nmcli_add_con_cmds
from utilities.network import get_vmi_ip_v4_by_name, sriov_network_dict
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


@pytest.fixture(scope="class")
def skip_insufficient_sriov_workers(sriov_workers):
    """
    This function will make sure atleast 2 worker nodes has SR-IOV capability
    else tests will be skip
    """
    if len(sriov_workers) < 2:
        pytest.skip(msg="Test requires at least 2 sriov worker nodes")


@pytest.fixture(scope="class")
def sriov_workers_node1(sriov_workers):
    """
    Get first worker nodes with sriov capabilities
    """
    return sriov_workers[0]


@pytest.fixture(scope="class")
def sriov_workers_node2(sriov_workers):
    """
    Get second worker nodes with sriov capabilities
    """
    return sriov_workers[1]


@pytest.fixture(scope="class")
def sriov_network(sriov_node_policy, namespace):
    """
    Create a sriov network linked to sriov policy.
    """
    with SriovNetwork(
        name="sriov-test-network",
        resource_name=sriov_node_policy.resource_name,
        policy_namespace=py_config["sriov_namespace"],
        network_namespace=namespace.name,
        vlan=0,
    ) as sriov_network:
        yield sriov_network


@pytest.fixture(scope="class")
def sriov_vm1(
    sriov_workers_node1, namespace, unprivileged_client, sriov_network,
):
    name = "sriov-vma1"
    networks = sriov_network_dict(namespace=namespace, network=sriov_network)
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["bootcmd"] = nmcli_add_con_cmds(iface="eth1", ip="10.200.1.1")

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=sriov_workers_node1.name,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="class")
def running_sriov_vm1(sriov_vm1):
    vmi = sriov_vm1.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    return vmi


@pytest.fixture(scope="class")
def sriov_vm2(
    sriov_workers_node2, namespace, unprivileged_client, sriov_network,
):
    name = "sriov-vma2"
    networks = sriov_network_dict(namespace=namespace, network=sriov_network)
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["bootcmd"] = nmcli_add_con_cmds(iface="eth1", ip="10.200.1.2")

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=sriov_workers_node2.name,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="class")
def running_sriov_vm2(sriov_vm2):
    vmi = sriov_vm2.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    return vmi


@pytest.mark.usefixtures("skip_rhel7_workers", "skip_insufficient_sriov_workers")
class TestPingConnectivity:
    @pytest.mark.polarion("CNV-3963")
    def test_sriov_basic_connectivity(
        self, sriov_network, sriov_vm1, sriov_vm2, running_sriov_vm1, running_sriov_vm2,
    ):

        assert_ping_successful(
            src_vm=running_sriov_vm1,
            dst_ip=get_vmi_ip_v4_by_name(
                vmi=running_sriov_vm2, name=sriov_network.name
            ),
        )
