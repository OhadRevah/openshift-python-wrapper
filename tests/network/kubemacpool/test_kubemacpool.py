import netaddr
import pytest
from tests.network.utils import assert_ping_successful


def ifaces_config_same(vm, vmi):
    """Compares vm and vmi interface configuration"""
    vm_temp_spec = vm.instance["spec"]["template"]["spec"]
    vm_interfaces = vm_temp_spec["domain"]["devices"]["interfaces"]
    vmi_interfaces = vmi.instance["spec"]["domain"]["devices"]["interfaces"]
    return vm_interfaces == vmi_interfaces


def mac_is_within_range(kubemacpool_range, mac):
    start_mac = netaddr.EUI(kubemacpool_range["data"]["RANGE_START"])
    end_mac = netaddr.EUI(kubemacpool_range["data"]["RANGE_END"])
    return int(start_mac) <= int(netaddr.EUI(mac)) <= int(end_mac)


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


def assert_mac_not_in_range_vms_connectivity_via_network(
    vm_a, vm_b, nad_name, kubemacpool
):
    for vm in (vm_a, vm_a):
        vm_nad_name = getattr(vm, nad_name).name
        assert not mac_is_within_range(
            kubemacpool_range=kubemacpool,
            mac=get_vmi_iface_mac_address_by_name(vmi=vm.vmi, name=vm_nad_name),
        )
        assert ifaces_config_same(vm=vm, vmi=vm.vmi)
    dst_ip_address = getattr(vm_b, nad_name).ip_address
    assert_ping_successful(src_vm=vm_a, dst_ip=dst_ip_address)


def assert_mac_static_vms_connectivity_via_network(vm_a, vm_b, nad_name):
    for vm in (vm_a, vm_a):
        vm_mac_address = getattr(vm, nad_name).mac_address
        vm_nad_name = getattr(vm, nad_name).name
        assert macs_are_the_same(
            vmi=vm.vmi, iface_name=vm_nad_name, expected_mac=vm_mac_address
        )
    dst_ip_address = getattr(vm_b, nad_name).ip_address
    assert_ping_successful(src_vm=vm_a, dst_ip=dst_ip_address)


def assert_mac_in_range_vms_connectivity_via_network(vm_a, vm_b, nad_name, kubemacpool):
    for vm in (vm_a, vm_a):
        assert mac_is_within_range(
            kubemacpool_range=kubemacpool,
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
    def test_manual_mac_from_pool(self, namespace, configured_vm_a, configured_vm_b):
        """Test that manually assigned mac address from pool is configured and working"""
        assert_mac_static_vms_connectivity_via_network(
            vm_a=configured_vm_a,
            vm_b=configured_vm_b,
            nad_name="manual_mac_iface_config",
        )

    @pytest.mark.polarion("CNV-2156")
    def test_manual_mac_not_from_pool(self, configured_vm_a, configured_vm_b):
        """Test that manually assigned mac address out of pool is configured and working"""
        assert_mac_static_vms_connectivity_via_network(
            vm_a=configured_vm_a,
            vm_b=configured_vm_b,
            nad_name="manual_mac_out_pool_iface_config",
        )

    @pytest.mark.polarion("CNV-2241")
    def test_automatic_mac_from_pool_pod_network(
        self, kubemacpool_first_scope, configured_vm_a, configured_vm_b
    ):
        """Test that automatic mac address assigned to POD's masquerade network
        from kubemacpool belongs to range and connectivity is OK"""
        assert_mac_in_range_vms_connectivity_via_network(
            vm_a=configured_vm_a,
            vm_b=configured_vm_b,
            nad_name="default_masquerade_iface_config",
            kubemacpool=kubemacpool_first_scope,
        )

    @pytest.mark.polarion("CNV-2155")
    def test_automatic_mac_from_pool(
        self, kubemacpool_first_scope, configured_vm_a, configured_vm_b
    ):
        """Test that automatic mac address assigned to interface
        from kubemacpool belongs to range and connectivity is OK"""
        assert_mac_in_range_vms_connectivity_via_network(
            vm_a=configured_vm_a,
            vm_b=configured_vm_b,
            nad_name="auto_mac_iface_config",
            kubemacpool=kubemacpool_first_scope,
        )

    @pytest.mark.polarion("CNV-2242")
    def test_automatic_mac_from_pool_tuning(
        self, kubemacpool_first_scope, configured_vm_a, configured_vm_b
    ):
        """Test that automatic mac address assigned to tuning interface
        from kubemacpool is belongs to range and connectivity is OK"""
        assert_mac_in_range_vms_connectivity_via_network(
            vm_a=configured_vm_a,
            vm_b=configured_vm_b,
            nad_name="auto_mac_tuning_iface_config",
            kubemacpool=kubemacpool_first_scope,
        )

    @pytest.mark.polarion("CNV-2157")
    def test_mac_preserved_after_shutdown(
        self, restarted_vmi_a, restarted_vmi_b, configured_vm_a, configured_vm_b
    ):
        """Test that all macs are preserved even after VM restart"""
        assert ifaces_config_same(vm=configured_vm_a, vmi=restarted_vmi_a)
        assert ifaces_config_same(vm=configured_vm_b, vmi=restarted_vmi_b)


@pytest.mark.usefixtures("skip_rhel7_workers")
class TestKubemacpoolChanged:
    #: TestKubemacpoolChanged setup
    # .........                                                                      ..........
    # |       |---eth0:           : POD network                  :auto:       eth0---|        |
    # |       |---eth1:10.200.1.1: Manual MAC          from pool:10.200.1.2:eth1---|        |
    # | VM-A  |---eth2:10.200.2.1: Automatic MAC       from pool:10.200.2.2:eth2---|  VM-B  |
    # |       |---eth3:10.200.3.1: Manual MAC not      from pool:10.200.3.2:eth3---|        |
    # |.......|---eth4:10.200.4.1: Automatic mac tuning network :10.200.4.2:eth4---|........|
    @pytest.mark.polarion("CNV-2158")
    def test_manual_mac_from_previous_pool(
        self, kubemacpool_second_scope, configured_vm_a, configured_vm_b
    ):
        """Test that mac manually configured from previous pool
        still the same and operational after kubemacpool's ConfigMap reconfiguration """
        assert_mac_static_vms_connectivity_via_network(
            vm_a=configured_vm_a,
            vm_b=configured_vm_b,
            nad_name="manual_mac_iface_config",
        )

    @pytest.mark.polarion("CNV-2160")
    def test_manual_mac_not_from_previous_pool(
        self, kubemacpool_second_scope, configured_vm_a, configured_vm_b
    ):
        """Test that mac manually configured with previous pool
        still the same and operational after kubemacpool's ConfiMap reconfiguration """
        assert_mac_static_vms_connectivity_via_network(
            vm_a=configured_vm_a,
            vm_b=configured_vm_b,
            nad_name="manual_mac_out_pool_iface_config",
        )

    @pytest.mark.polarion("CNV-2244")
    def test_automatic_mac_previous_pool_pod_masquerade(
        self, kubemacpool_second_scope, configured_vm_a, configured_vm_b
    ):
        """Test that Pod's mac automatically configured from previous pool
        still the same, doesn't belong to the new pool and operational
        after kubemacpool's ConfiMap reconfiguration """
        assert_mac_not_in_range_vms_connectivity_via_network(
            vm_a=configured_vm_a,
            vm_b=configured_vm_b,
            nad_name="default_masquerade_iface_config",
            kubemacpool=kubemacpool_second_scope,
        )

    @pytest.mark.polarion("CNV-2159")
    def test_automatic_mac_from_previous_pool(
        self, kubemacpool_second_scope, configured_vm_a, configured_vm_b
    ):
        """Test that mac automatically configured from previous pool
        still the same, doesn't belong to the new pool and operational
        after kubemacpool's ConfiMap reconfiguration """
        assert_mac_not_in_range_vms_connectivity_via_network(
            vm_a=configured_vm_a,
            vm_b=configured_vm_b,
            nad_name="auto_mac_iface_config",
            kubemacpool=kubemacpool_second_scope,
        )


@pytest.mark.usefixtures("skip_rhel7_workers")
class TestMacFromNewKubemacpoolRange:
    #: TestMacFromNewKubemacpoolRange setup
    # .........                                                               ..........
    # |       |---eth0:           :Automatic MAC from pool:         ---eth0---|        |
    # |       |---eth1:10.200.1.1:Automatic MAC from pool:10.200.1.2:eth1---|        |
    # | VM-A  |---eth2:10.200.2.1:Automatic MAC from pool:10.200.2.2:eth2---|  VM-B  |
    # | (NEW) |---eth3:10.200.3.1:Automatic MAC from pool:10.200.3.2:eth3---|  (NEW) |
    # |.......|---eth4:10.200.4.1:Automatic MAC from pool:10.200.4.2:eth4---|........|
    @pytest.mark.polarion("CNV-2161")
    def test_automatic_new_mac_new_vm(
        self,
        namespace,
        kubemacpool_second_scope,
        started_vmi_c,
        started_vmi_d,
        booted_vm_c,
        booted_vm_d,
    ):
        """Test that new vms get mac addresses from the new range."""
        for vm in (started_vmi_c, started_vmi_d):
            ifaces = vm.instance["status"]["interfaces"]
            for iface in ifaces:
                assert mac_is_within_range(
                    kubemacpool_range=kubemacpool_second_scope, mac=iface["mac"]
                )
        assert_ping_successful(
            src_vm=booted_vm_c, dst_ip=booted_vm_d.auto_mac_iface_config.ip_address
        )
