# -*- coding: utf-8 -*-

"""
VM to VM connectivity
"""

import pytest
from pytest_testconfig import config as py_config

from tests.fixtures import (
    create_resources_from_yaml,
    create_vms_from_template,
    wait_until_vmis_running,
    wait_for_vmis_interfaces_report,
    start_vms,
)
from tests import utils
from tests.network.connectivity.fixtures import create_bond
from tests.network.fixtures import update_vms_pod_ip_info
from . import config
from .fixtures import (
    create_ovs_bridge_on_vxlan,
    create_ovs_bridges_real_nics,
    attach_ovs_bridge_to_bond,
)

pytestmark = pytest.mark.skip("Skip until OVS is supported")


@pytest.mark.usefixtures(
    create_resources_from_yaml.__name__,
    create_ovs_bridges_real_nics.__name__,
    create_ovs_bridge_on_vxlan.__name__,
    create_bond.__name__,
    attach_ovs_bridge_to_bond.__name__,
    create_vms_from_template.__name__,
    start_vms.__name__,
    wait_until_vmis_running.__name__,
    wait_for_vmis_interfaces_report.__name__,
    update_vms_pod_ip_info.__name__,
)
class TestConnectivity(object):
    """
    Test VM to VM connectivity
    """
    namespace = config.NETWORK_NS
    vms = config.VMS
    template = config.VM_YAML_FEDORA
    template_kwargs = config.VM_FEDORA_ATTRS
    bond_name = config.BOND_1
    yamls = [
        config.OVS_NET_YAML,
        config.OVS_BOND_YAML,
        config.OVS_NET_VLAN_100_YAML,
        config.OVS_NET_VLAN_200_YAML,
        config.OVS_NET_VLAN_300_YAML,
    ]
    src_vm = list(config.VMS.keys())[0]
    dst_vm = list(config.VMS.keys())[1]

    @pytest.mark.parametrize(
        'bridge',
        [
            pytest.param('pod'),
            pytest.param(config.BRIDGE_BR1),
            pytest.param(config.BRIDGE_BR1VLAN100),
            pytest.param(config.BRIDGE_BR1BOND),
            pytest.param(config.BRIDGE_BR1VLAN200)
        ],
        ids=[
            'Connectivity_between_VM_to_VM_over_POD_network',
            'Connectivity_between_VM_to_VM_over_L2_OVS_network',
            'Connectivity_between_VM_to_VM_over_L2_OVS_VLAN_network',
            'Connectivity_between_VM_to_VM_over_L2_OVS_on_BOND_network',
            'Negative:No_connectivity_between_VM_to_VM_L2_OVS_different_VLANs'
        ]
    )
    def test_connectivity(self, bridge, bond_supported):
        """
        Check connectivity
        """
        if bridge == config.BRIDGE_BR1BOND:
            if not bond_supported:
                pytest.skip(msg='No BOND support')

        positive = True
        if bridge == config.BRIDGE_BR1VLAN200:
            dst_ip = self.vms[self.dst_vm]["interfaces"][config.BRIDGE_BR1VLAN300][0]
            positive = False
        else:
            dst_ip = self.vms[self.dst_vm]["interfaces"][bridge][0]

        utils.run_test_connectivity(
            src_vm=self.src_vm, dst_vm=self.dst_vm, dst_ip=dst_ip, positive=positive
        )

    @pytest.mark.parametrize(
        'interface_id',
        [
            pytest.param('pod'),
            pytest.param(config.BRIDGE_BR1),
        ],
        ids=[
            'test_guest_performance_over_POD_network',
            'test_guest_performance_over_L2_Linux_bridge_network',
        ]
    )
    def test_guest_performance(self, interface_id):
        """
        In-guest performance bandwidth passthrough over OVS
        """
        if not pytest.real_nics_env:
            pytest.skip(msg='Only run on bare metal env')

        expected_res = py_config['test_guest_performance']['bandwidth']
        listen_ip = self.src_vm["interfaces"][interface_id][0]
        bits_per_second = utils.run_test_guest_performance(
            server_vm=self.src_vm, client_vm=self.src_vm, listen_ip=listen_ip
        )
        assert bits_per_second >= expected_res
