"""
Sriov Tests
"""
import pytest
from pytest_testconfig import config as py_config
from resources.sriov_network import SriovNetwork
from tests.network.utils import (
    assert_no_ping,
    assert_ping_successful,
    nmcli_add_con_cmds,
)
from utilities.infra import BUG_STATUS_CLOSED, get_bug_status
from utilities.network import get_vmi_ip_v4_by_name, sriov_network_dict
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


@pytest.fixture(scope="class")
def iface_search_mac(bugzilla_connection_params):
    # TODO : Remove iface_search_mac when BZ 1868359 is fixed.
    # TODO : JIRA Task :  https://issues.redhat.com/browse/CNV-6349
    # Interface will fallback to eth1 automatically when bug is closed/verified/on_qa.
    if (
        get_bug_status(
            bugzilla_connection_params=bugzilla_connection_params, bug=1868359
        )
        not in BUG_STATUS_CLOSED
    ):
        return "$(ip --brief l | grep '02:00:b5:b5:b5:' | cut -f1 -d' ')"
    return "eth1"


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
    ) as sriov_network:
        yield sriov_network


@pytest.fixture(scope="class")
def sriov_network_vlan(sriov_node_policy, namespace, vlan_id):
    """
    Create a sriov network linked to sriov policy.
    """
    with SriovNetwork(
        name="sriov-test-network-vlan",
        resource_name=sriov_node_policy.resource_name,
        policy_namespace=py_config["sriov_namespace"],
        network_namespace=namespace.name,
        vlan=vlan_id,
    ) as sriov_network:
        yield sriov_network


@pytest.fixture(scope="class")
def sriov_vm1(
    sriov_workers_node1, namespace, unprivileged_client, sriov_network, iface_search_mac
):
    name = "sriov-vm1"
    networks = sriov_network_dict(namespace=namespace, network=sriov_network)
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["userData"]["bootcmd"] = nmcli_add_con_cmds(
        iface=iface_search_mac, ip="10.200.1.1"
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
def sriov_vm2(
    sriov_workers_node2, namespace, unprivileged_client, sriov_network, iface_search_mac
):
    name = "sriov-vm2"
    networks = sriov_network_dict(namespace=namespace, network=sriov_network)
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["userData"]["bootcmd"] = nmcli_add_con_cmds(
        iface=iface_search_mac, ip="10.200.1.2"
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
    iface_search_mac,
):
    name = "sriov-vm3"
    networks = sriov_network_dict(namespace=namespace, network=sriov_network_vlan)
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["userData"]["bootcmd"] = nmcli_add_con_cmds(
        iface=iface_search_mac, ip="10.200.3.1"
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
    iface_search_mac,
):
    name = "sriov-vm4"
    networks = sriov_network_dict(namespace=namespace, network=sriov_network_vlan)
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data["userData"]["bootcmd"] = nmcli_add_con_cmds(
        iface=iface_search_mac, ip="10.200.3.2"
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


@pytest.mark.usefixtures(
    "skip_rhel7_workers", "skip_if_no_sriov_workers", "skip_insufficient_sriov_workers"
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
