"""
VM to VM connectivity via secondary (bridged) interfaces.
"""
from collections import OrderedDict

import pytest
from pytest_testconfig import config as py_config
from tests.network.connectivity.utils import run_test_guest_performance
from tests.network.utils import assert_no_ping
from utilities.infra import BUG_STATUS_CLOSED
from utilities.network import (
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
def ovs_linux_nad(bridge_device_matrix__class__, namespace, network_interface):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="br1test-nad",
        interface_name=network_interface.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def ovs_linux_br1vlan100_nad(
    bridge_device_matrix__class__, namespace, network_interface
):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="br1vlan100-nad",
        interface_name=network_interface.bridge_name,
        vlan=100,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def ovs_linux_br1vlan200_nad(
    bridge_device_matrix__class__, namespace, network_interface
):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="br1vlan200-nad",
        interface_name=network_interface.bridge_name,
        vlan=200,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def ovs_linux_br1vlan300_nad(
    bridge_device_matrix__class__, namespace, network_interface
):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="br1vlan300-nad",
        interface_name=network_interface.bridge_name,
        vlan=300,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def ovs_linux_bridge_attached_vma(
    worker_node1,
    namespace,
    unprivileged_client,
    ovs_linux_nad,
    ovs_linux_br1vlan100_nad,
    ovs_linux_br1vlan200_nad,
):
    name = "vma"
    networks = OrderedDict()
    networks[ovs_linux_nad.name] = ovs_linux_nad.name
    networks[ovs_linux_br1vlan100_nad.name] = ovs_linux_br1vlan100_nad.name
    networks[ovs_linux_br1vlan200_nad.name] = ovs_linux_br1vlan200_nad.name
    network_data_data = {
        "ethernets": {
            "eth1": {"addresses": ["10.200.0.1/24"]},
            "eth2": {"addresses": ["10.200.1.1/24"]},
            "eth3": {"addresses": ["10.200.2.1/24"]},
        }
    }
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
def ovs_linux_bridge_attached_vmb(
    worker_node2,
    namespace,
    unprivileged_client,
    ovs_linux_nad,
    ovs_linux_br1vlan100_nad,
    ovs_linux_br1vlan300_nad,
):
    name = "vmb"
    networks = OrderedDict()
    networks[ovs_linux_nad.name] = ovs_linux_nad.name
    networks[ovs_linux_br1vlan100_nad.name] = ovs_linux_br1vlan100_nad.name
    networks[ovs_linux_br1vlan300_nad.name] = ovs_linux_br1vlan300_nad.name
    network_data_data = {
        "ethernets": {
            "eth1": {"addresses": ["10.200.0.2/24"]},
            "eth2": {"addresses": ["10.200.1.2/24"]},
            "eth3": {"addresses": ["10.200.2.2/24"]},
        }
    }

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
def ovs_linux_bridge_attached_running_vmia(ovs_linux_bridge_attached_vma):
    vmi = ovs_linux_bridge_attached_vma.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    return vmi


@pytest.fixture(scope="class")
def ovs_linux_bridge_attached_running_vmib(ovs_linux_bridge_attached_vmb):
    vmi = ovs_linux_bridge_attached_vmb.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    return vmi


@pytest.mark.usefixtures("skip_rhel7_workers", "skip_when_one_node")
class TestConnectivity:
    @pytest.mark.parametrize(
        "bridge",
        [
            pytest.param(
                "default",
                marks=(pytest.mark.polarion("CNV-2350")),
                id="Connectivity_between_VM_to_VM_over_POD_network_make_sure_it_works_while_L2_networks_exists",
            ),
            pytest.param(
                "br1test-nad",
                marks=(pytest.mark.polarion("CNV-2080")),
                id="Connectivity_between_VM_to_VM_over_L2_bridge_network",
            ),
        ],
    )
    def test_bridge(
        self,
        skip_if_no_multinic_nodes,
        bridge,
        rhel7_workers,
        namespace,
        network_interface,
        ovs_linux_bridge_attached_vma,
        ovs_linux_bridge_attached_vmb,
        ovs_linux_bridge_attached_running_vmia,
        ovs_linux_bridge_attached_running_vmib,
    ):
        if bridge == "default" and rhel7_workers:
            # https://bugzilla.redhat.com/show_bug.cgi?id=1787576
            pytest.skip(msg="Masquerade not working on RHEL7 workers.")

        assert_ping_successful(
            src_vm=ovs_linux_bridge_attached_running_vmia,
            dst_ip=_masquerade_vmib_ip(ovs_linux_bridge_attached_running_vmib, bridge),
        )

    @pytest.mark.polarion("CNV-2072")
    def test_positive_vlan(
        self,
        skip_rhel7_workers,
        skip_if_no_multinic_nodes,
        skip_if_workers_vms,
        namespace,
        network_interface,
        ovs_linux_br1vlan100_nad,
        ovs_linux_bridge_attached_vma,
        ovs_linux_bridge_attached_vmb,
        ovs_linux_bridge_attached_running_vmia,
        ovs_linux_bridge_attached_running_vmib,
    ):
        assert_ping_successful(
            src_vm=ovs_linux_bridge_attached_running_vmia,
            dst_ip=get_vmi_ip_v4_by_name(
                vmi=ovs_linux_bridge_attached_running_vmib,
                name=ovs_linux_br1vlan100_nad.name,
            ),
        )

    @pytest.mark.bugzilla(
        1827257, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    @pytest.mark.polarion("CNV-2075")
    def test_negative_vlan(
        self,
        skip_rhel7_workers,
        skip_if_workers_vms,
        skip_if_no_multinic_nodes,
        namespace,
        network_interface,
        ovs_linux_br1vlan300_nad,
        ovs_linux_bridge_attached_vma,
        ovs_linux_bridge_attached_vmb,
        ovs_linux_bridge_attached_running_vmia,
        ovs_linux_bridge_attached_running_vmib,
    ):
        assert_no_ping(
            src_vm=ovs_linux_bridge_attached_running_vmia,
            dst_ip=get_vmi_ip_v4_by_name(
                vmi=ovs_linux_bridge_attached_running_vmib,
                name=ovs_linux_br1vlan300_nad.name,
            ),
        )

    @pytest.mark.xfail(reason="Slow performance on BM, need investigation")
    @pytest.mark.polarion("CNV-2335")
    def test_guest_performance(
        self,
        skip_rhel7_workers,
        skip_if_workers_vms,
        skip_if_no_multinic_nodes,
        namespace,
        network_interface,
        ovs_linux_nad,
        ovs_linux_bridge_attached_vma,
        ovs_linux_bridge_attached_vmb,
        ovs_linux_bridge_attached_running_vmia,
        ovs_linux_bridge_attached_running_vmib,
    ):
        """
        In-guest performance bandwidth passthrough.
        """
        expected_res = py_config["test_guest_performance"]["bandwidth"]
        bits_per_second = run_test_guest_performance(
            server_vm=ovs_linux_bridge_attached_vma,
            client_vm=ovs_linux_bridge_attached_vmb,
            listen_ip=get_vmi_ip_v4_by_name(
                vmi=ovs_linux_bridge_attached_running_vmia, name=ovs_linux_nad.name
            ),
        )
        assert bits_per_second >= expected_res
