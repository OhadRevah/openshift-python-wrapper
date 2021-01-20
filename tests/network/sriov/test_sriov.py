"""
SRIOV Tests
"""

import logging

import pytest
from pytest_testconfig import config as py_config
from resources.sriov_network import SriovNetwork

from tests.network.utils import assert_no_ping
from utilities import console
from utilities.infra import (
    BUG_STATUS_CLOSED,
    get_bug_status,
    get_bugzilla_connection_params,
)
from utilities.network import (
    assert_ping_successful,
    cloud_init_network_data,
    get_vmi_ip_v4_by_name,
    sriov_network_dict,
)
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    vm_console_run_commands,
    wait_for_vm_interfaces,
)


LOGGER = logging.getLogger(__name__)
SRIOV_NAMESPACE = py_config["sriov_namespace"]


# TODO : remove restart_guest_agent and replace all calls to it with wait_for_vm_interfaces once BZ 1907707 is fixed
def restart_guest_agent(vm):
    bug_num = 1907707
    if (
        get_bug_status(
            bugzilla_connection_params=get_bugzilla_connection_params(), bug=bug_num
        )
        not in BUG_STATUS_CLOSED
    ):
        vm_console_run_commands(
            console_impl=console.Fedora,
            vm=vm,
            commands=["sudo systemctl restart qemu-guest-agent"],
        )
    else:
        LOGGER.warning(
            f"bug {bug_num} is resolved. please remove all references to it from the automation"
        )
    wait_for_vm_interfaces(vmi=vm.vmi)


def running_vmi(vm):
    vmi = vm.vmi
    vmi.wait_until_running()
    restart_guest_agent(vm=vm)
    return vmi


@pytest.fixture(scope="class")
def skip_insufficient_sriov_workers(sriov_workers):
    """
    This function will make sure at least 2 worker nodes has SRIOV capability
    else tests will be skip.
    """
    if len(sriov_workers) < 2:
        pytest.skip(msg="Test requires at least 2 SRIOV worker nodes")


@pytest.fixture(scope="class")
def sriov_workers_node1(sriov_workers):
    """
    Get first worker nodes with SRIOV capabilities
    """
    return sriov_workers[0]


@pytest.fixture(scope="class")
def sriov_workers_node2(sriov_workers):
    """
    Get second worker nodes with SRIOV capabilities
    """
    return sriov_workers[1]


@pytest.fixture(scope="class")
def sriov_network(sriov_node_policy, namespace):
    """
    Create a SRIOV network linked to SRIOV policy.
    """
    with SriovNetwork(
        name="sriov-test-network",
        resource_name=sriov_node_policy.resource_name,
        namespace=SRIOV_NAMESPACE,
        network_namespace=namespace.name,
    ) as sriov_network:
        yield sriov_network


@pytest.fixture(scope="class")
def sriov_network_vlan(sriov_node_policy, namespace, vlan_tag_id):
    """
    Create a SRIOV network linked to SRIOV policy.
    """
    with SriovNetwork(
        name="sriov-test-network-vlan",
        resource_name=sriov_node_policy.resource_name,
        namespace=SRIOV_NAMESPACE,
        network_namespace=namespace.name,
        vlan=vlan_tag_id,
    ) as sriov_network:
        yield sriov_network


@pytest.fixture(scope="class")
def sriov_vm1(sriov_workers_node1, namespace, unprivileged_client, sriov_network):
    name = "sriov-vm1"
    networks = sriov_network_dict(namespace=namespace, network=sriov_network)
    network_data_data = {"ethernets": {"eth1": {"addresses": ["10.200.1.1/24"]}}}
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data.update(cloud_init_network_data(data=network_data_data))

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
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
    return running_vmi(vm=sriov_vm1)


@pytest.fixture(scope="class")
def sriov_vm2(sriov_workers_node2, namespace, unprivileged_client, sriov_network):
    name = "sriov-vm2"
    networks = sriov_network_dict(namespace=namespace, network=sriov_network)
    network_data_data = {"ethernets": {"eth1": {"addresses": ["10.200.1.2/24"]}}}
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data.update(cloud_init_network_data(data=network_data_data))

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
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
    return running_vmi(vm=sriov_vm2)


@pytest.fixture(scope="class")
def sriov_vm3(
    sriov_workers_node1,
    namespace,
    unprivileged_client,
    sriov_network_vlan,
):
    name = "sriov-vm3"
    networks = sriov_network_dict(namespace=namespace, network=sriov_network_vlan)
    network_data_data = {"ethernets": {"eth1": {"addresses": ["10.200.3.1/24"]}}}
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data.update(cloud_init_network_data(data=network_data_data))

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=sriov_workers_node1.name,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="class")
def running_sriov_vm3(sriov_vm3):
    return running_vmi(vm=sriov_vm3)


@pytest.fixture(scope="class")
def sriov_vm4(
    sriov_workers_node2,
    namespace,
    unprivileged_client,
    sriov_network_vlan,
):
    name = "sriov-vm4"
    networks = sriov_network_dict(namespace=namespace, network=sriov_network_vlan)
    network_data_data = {"ethernets": {"eth1": {"addresses": ["10.200.3.2/24"]}}}
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data.update(cloud_init_network_data(data=network_data_data))

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=sriov_workers_node2.name,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
        ssh=True,
        username=console.Fedora.USERNAME,
        password=console.Fedora.PASSWORD,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="class")
def running_sriov_vm4(sriov_vm4):
    return running_vmi(vm=sriov_vm4)


@pytest.fixture(scope="class")
def vm4_interfaces(running_sriov_vm4):
    return running_sriov_vm4.interfaces


@pytest.mark.usefixtures(
    "skip_when_no_sriov",
    "labeled_sriov_nodes",
    "skip_rhel7_workers",
    "skip_insufficient_sriov_workers",
)
class TestPingConnectivity:
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
            dst_ip=get_vmi_ip_v4_by_name(
                vmi=running_sriov_vm2, name=sriov_network.name
            ),
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
                vmi=running_sriov_vm4, name=sriov_network_vlan.name
            ),
        )

    @pytest.mark.polarion("CNV-4713")
    def test_sriov_no_connectivity_no_vlan_to_vlan(
        self, sriov_network_vlan, running_sriov_vm1, running_sriov_vm4
    ):
        assert_no_ping(
            src_vm=running_sriov_vm1,
            dst_ip=get_vmi_ip_v4_by_name(
                vmi=running_sriov_vm4, name=sriov_network_vlan.name
            ),
        )

    @pytest.mark.polarion("CNV-4768")
    def test_sriov_interfaces_post_reboot(
        self, workers_ssh_executors, sriov_vm4, running_sriov_vm4, vm4_interfaces
    ):
        sriov_vm4.ssh_exec.run_command(command=["sudo", "reboot"])
        # Make sure the VM is down.
        sriov_vm4.ssh_exec.executor().wait_for_connectivity_state(positive=False)
        # Make sure the VM is up, otherwise we will get an old VM interfaces data.
        sriov_vm4.ssh_exec.executor().wait_for_connectivity_state(positive=True)
        restart_guest_agent(vm=sriov_vm4)
        # Check only the second interface (SRIOV interface).
        assert running_sriov_vm4.interfaces[1] == vm4_interfaces[1]
