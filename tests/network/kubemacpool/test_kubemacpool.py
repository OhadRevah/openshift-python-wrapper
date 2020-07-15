import pytest
from kubernetes.client.rest import ApiException
from tests.network.utils import assert_ping_successful
from utilities.virt import VirtualMachineForTests


def ifaces_config_same(vm, vmi):
    """Compares vm and vmi interface configuration"""
    vm_temp_spec = vm.instance["spec"]["template"]["spec"]
    vm_interfaces = vm_temp_spec["domain"]["devices"]["interfaces"]
    vmi_interfaces = vmi.instance["spec"]["domain"]["devices"]["interfaces"]
    return vm_interfaces == vmi_interfaces


class IfaceNotFound(Exception):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"Interface not found for NAD {self.name}"


def get_vmi_iface_mac_address_by_name(vmi, name):
    for iface in vmi.interfaces:
        if iface.name == name:
            return iface.mac
    raise IfaceNotFound(name)


def macs_are_the_same(vmi, expected_mac, iface_name):
    actual_vmi_interface_mac_address = get_vmi_iface_mac_address_by_name(
        vmi=vmi, name=iface_name
    )
    return actual_vmi_interface_mac_address == expected_mac


def assert_mac_not_in_range(vm, nad_name, mac_pool):
    assert not mac_pool.mac_is_within_range(
        mac=get_vmi_iface_mac_address_by_name(vmi=vm.vmi, name=nad_name)
    )


def assert_mac_static_vms_connectivity_via_network(vm_a, vm_b, nad_name):
    for vm in (vm_a, vm_a):
        vm_mac_address = getattr(vm, nad_name).mac_address
        vm_nad_name = getattr(vm, nad_name).name
        assert macs_are_the_same(
            vmi=vm.vmi, iface_name=vm_nad_name, expected_mac=vm_mac_address
        )
    dst_ip_address = getattr(vm_b, nad_name).ip_address
    assert_ping_successful(src_vm=vm_a, dst_ip=dst_ip_address)


def assert_mac_in_range_vms_connectivity_via_network(vm_a, vm_b, nad_name, mac_pool):
    for vm in (vm_a, vm_a):
        assert mac_pool.mac_is_within_range(
            mac=get_vmi_iface_mac_address_by_name(
                vmi=vm.vmi, name=vm.auto_mac_iface_config.name
            ),
        )
    dst_ip_address = getattr(vm_b, nad_name).ip_address
    assert_ping_successful(src_vm=vm_a, dst_ip=dst_ip_address)


@pytest.mark.usefixtures("skip_rhel7_workers")
class TestConnectivity:
    #: TestConnectivity setup
    # .........                                                                      ..........
    # |       |---eth0:           : POD network                  :auto:       eth0---|        |
    # |       |---eth1:10.200.1.1: Manual MAC          from pool:10.200.1.2:eth1---|        |
    # | VM-A  |---eth2:10.200.2.1: Automatic MAC       from pool:10.200.2.2:eth2---|  VM-B  |
    # |       |---eth3:10.200.3.1: Manual MAC not      from pool:10.200.3.2:eth3---|        |
    # |.......|---eth4:10.200.4.1: Automatic mac tuning network :10.200.4.2:eth4---|........|
    @pytest.mark.polarion("CNV-2154")
    def test_manual_mac_from_pool(
        self, namespace, started_vmi_a, started_vmi_b, running_vm_a, running_vm_b
    ):
        """Test that manually assigned mac address from pool is configured and working"""
        assert_mac_static_vms_connectivity_via_network(
            vm_a=running_vm_a, vm_b=running_vm_b, nad_name="manual_mac_iface_config",
        )

    @pytest.mark.polarion("CNV-2156")
    def test_manual_mac_not_from_pool(self, running_vm_a, running_vm_b):
        """Test that manually assigned mac address out of pool is configured and working"""
        assert_mac_static_vms_connectivity_via_network(
            vm_a=running_vm_a,
            vm_b=running_vm_b,
            nad_name="manual_mac_out_pool_iface_config",
        )

    @pytest.mark.polarion("CNV-2241")
    def test_automatic_mac_from_pool_pod_network(
        self, mac_pool, running_vm_a, running_vm_b
    ):
        """Test that automatic mac address assigned to POD's masquerade network
        from kubemacpool belongs to range and connectivity is OK"""
        assert_mac_in_range_vms_connectivity_via_network(
            vm_a=running_vm_a,
            vm_b=running_vm_b,
            nad_name="default_masquerade_iface_config",
            mac_pool=mac_pool,
        )

    @pytest.mark.polarion("CNV-2155")
    def test_automatic_mac_from_pool(self, mac_pool, running_vm_a, running_vm_b):
        """Test that automatic mac address assigned to interface
        from kubemacpool belongs to range and connectivity is OK"""
        assert_mac_in_range_vms_connectivity_via_network(
            vm_a=running_vm_a,
            vm_b=running_vm_b,
            nad_name="auto_mac_iface_config",
            mac_pool=mac_pool,
        )

    @pytest.mark.polarion("CNV-2242")
    def test_automatic_mac_from_pool_tuning(self, mac_pool, running_vm_a, running_vm_b):
        """Test that automatic mac address assigned to tuning interface
        from kubemacpool is belongs to range and connectivity is OK"""
        assert_mac_in_range_vms_connectivity_via_network(
            vm_a=running_vm_a,
            vm_b=running_vm_b,
            nad_name="auto_mac_tuning_iface_config",
            mac_pool=mac_pool,
        )

    @pytest.mark.polarion("CNV-2157")
    def test_mac_preserved_after_shutdown(
        self, restarted_vmi_a, restarted_vmi_b, running_vm_a, running_vm_b
    ):
        """Test that all macs are preserved even after VM restart"""
        assert ifaces_config_same(vm=running_vm_a, vmi=restarted_vmi_a)
        assert ifaces_config_same(vm=running_vm_b, vmi=restarted_vmi_b)


class TestNegatives:
    @pytest.mark.polarion("CNV-4199")
    def test_opted_out_ns(
        self, mac_pool, opted_out_ns, opted_out_ns_nad, opted_out_ns_vm,
    ):
        assert_mac_not_in_range(
            vm=opted_out_ns_vm, nad_name=opted_out_ns_nad.name, mac_pool=mac_pool,
        )

    @pytest.mark.polarion("CNV-4217")
    def test_wrong_label_ns(
        self, mac_pool, wrong_label_ns, wrong_label_ns_nad, wrong_label_ns_vm,
    ):
        assert_mac_not_in_range(
            vm=wrong_label_ns_vm, nad_name=wrong_label_ns_nad.name, mac_pool=mac_pool,
        )


@pytest.mark.polarion("CNV-4405")
def test_kmp_down(namespace, kmp_down):
    with pytest.raises(ApiException):
        with VirtualMachineForTests(name="kmp-down-vm", namespace=namespace.name):
            return


@pytest.mark.destructive
@pytest.mark.polarion("CNV-3979")
def test_kmp_crash_loop(
    skip_if_no_ovn,
    namespace,
    kmp_crash_loop,
    deleted_ovnkube_node_pod,
    ovnkube_node_daemonset,
):
    ovnkube_node_daemonset.wait_until_deployed()
