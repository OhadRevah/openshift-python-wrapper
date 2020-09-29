"""
SRIOV Tests
"""

import pytest
from pytest_testconfig import config as py_config
from resources.sriov_network import SriovNetwork
from resources.utils import TimeoutSampler
from tests.network.utils import (
    assert_no_ping,
    assert_ping_successful,
    nmcli_add_con_cmds,
)
from utilities import console
from utilities.network import get_vmi_ip_v4_by_name, sriov_network_dict
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    vm_console_run_commands,
    wait_for_vm_interfaces,
)


SRIOV_NAMESPACE = py_config["sriov_namespace"]


def _ping_sampler(node_exec, command, positive):
    """
    Wait until PING is return or not based on positive value.
    """
    sampler = TimeoutSampler(
        timeout=60, sleep=1, func=node_exec.run_command, command=command
    )
    for sample in sampler:
        rc = sample[0]
        if rc and not positive:
            return

        if not rc and positive:
            return


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
        policy_namespace=SRIOV_NAMESPACE,
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
        policy_namespace=SRIOV_NAMESPACE,
        network_namespace=namespace.name,
        vlan=vlan_tag_id,
    ) as sriov_network:
        yield sriov_network


@pytest.fixture(scope="class")
def sriov_vm1(sriov_workers_node1, namespace, unprivileged_client, sriov_network):
    name = "sriov-vm1"
    networks = sriov_network_dict(namespace=namespace, network=sriov_network)
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["userData"]["bootcmd"] = nmcli_add_con_cmds(
        iface="eth1", ip="10.200.1.1"
    )

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
    vmi = sriov_vm1.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    return vmi


@pytest.fixture(scope="class")
def sriov_vm2(sriov_workers_node2, namespace, unprivileged_client, sriov_network):
    name = "sriov-vm2"
    networks = sriov_network_dict(namespace=namespace, network=sriov_network)
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["userData"]["bootcmd"] = nmcli_add_con_cmds(
        iface="eth1", ip="10.200.1.2"
    )

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
    vmi = sriov_vm2.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    return vmi


@pytest.fixture(scope="class")
def sriov_vm3(
    sriov_workers_node1,
    namespace,
    unprivileged_client,
    sriov_network_vlan,
):
    name = "sriov-vm3"
    networks = sriov_network_dict(namespace=namespace, network=sriov_network_vlan)
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["userData"]["bootcmd"] = nmcli_add_con_cmds(
        iface="eth1", ip="10.200.3.1"
    )

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
    vmi = sriov_vm3.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    return vmi


@pytest.fixture(scope="class")
def sriov_vm4(
    sriov_workers_node2,
    namespace,
    unprivileged_client,
    sriov_network_vlan,
):
    name = "sriov-vm4"
    networks = sriov_network_dict(namespace=namespace, network=sriov_network_vlan)
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["userData"]["bootcmd"] = nmcli_add_con_cmds(
        iface="eth1", ip="10.200.3.2"
    )

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
def running_sriov_vm4(sriov_vm4):
    vmi = sriov_vm4.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    return vmi


@pytest.fixture(scope="class")
def vm4_interfaces(running_sriov_vm4):
    return running_sriov_vm4.interfaces


@pytest.mark.usefixtures(
    "skip_rhel7_workers",
    "skip_if_no_sriov_workers",
    "skip_insufficient_sriov_workers",
    "sriov_vm1",
    "sriov_vm2",
    "sriov_vm3",
    "sriov_vm4",
    "running_sriov_vm1",
    "running_sriov_vm2",
    "running_sriov_vm3",
    "running_sriov_vm4",
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
        vm_console_run_commands(
            console_impl=console.Fedora,
            vm=sriov_vm4,
            commands=["sudo reboot -f now"],
            verify_commands_output=False,
        )

        pod_ip = str(get_vmi_ip_v4_by_name(vmi=running_sriov_vm4, name="default"))
        node_exec = workers_ssh_executors[running_sriov_vm4.node.name]
        command = ["ping", "-c", "1", pod_ip]
        # Make sure the VM is down.
        _ping_sampler(node_exec=node_exec, command=command, positive=False)

        # Make sure the VM is up, otherwise we will get an old VM interfaces data.
        _ping_sampler(node_exec=node_exec, command=command, positive=True)

        wait_for_vm_interfaces(vmi=running_sriov_vm4)
        # Check only the second interface (SRIOV interface).
        assert running_sriov_vm4.interfaces[1] == vm4_interfaces[1]
