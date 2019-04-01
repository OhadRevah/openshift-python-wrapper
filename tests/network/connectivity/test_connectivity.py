# -*- coding: utf-8 -*-

"""
VM to VM connectivity
"""
import json
import logging

import bitmath
import pytest
from autologs.autologs import generate_logs

from resources.pod import Pod
from resources.virtual_machine import VirtualMachine
from utilities import console, utils

from . import config
from .fixtures import (  # noqa: F401
    create_bond,
    create_networks_from_yaml,
    create_ovs_bridge_on_vxlan,
    create_ovs_bridges_real_nics,
    create_vms,
    get_node_internal_ip,
    get_ovs_cni_pods,
    is_bare_metal,
    is_bond_supported,
    prepare_env,
    wait_for_vms_status,
    create_privileged_user,
    create_privileged_pods,
)


LOGGER = logging.getLogger(__name__)


class TestConnectivity(object):
    """
    Test VM to VM connectivity
    """
    src_vm = config.VMS_LIST[0]
    dst_vm = config.VMS_LIST[1]

    @pytest.mark.parametrize(
        'ip',
        [
            pytest.param('pod_ip'),
            pytest.param('ovs_ip'),
            pytest.param('bond_ip'),
            pytest.param('non_vlan_ip')
        ],
        ids=[
            'Connectivity_between_VM_and_VM_over_POD_network',
            'Connectivity_between_VM_and_VM_over_Multus_with_OVS_network',
            'Connectivity_between_VM_and_VM_over_Multus_with_OVS_on_BOND_network',
            'Negative:_No_connectivity_from_non_VLAN_to_VLAN'
        ]
    )
    def test_connectivity(self, ip):
        """
        Check connectivity
        """
        if ip == 'bond_ip':
            if not pytest.bond_support_env:
                pytest.skip(msg='No BOND support')

        _id = utils.get_test_parametrize_ids(item=self.test_connectivity.pytestmark, params=ip)
        LOGGER.info(_id)
        positive = ip != 'non_vlan_ip'
        dst_ip = config.VMS.get(self.dst_vm).get(ip) if positive else config.OVS_NODES_IPS[0]
        with console.Console(vm=self.src_vm, distro='fedora', namespace=config.NETWORK_NS) as src_vm_console:
            src_vm_console.sendline('ping -w 3 {ip}'.format(ip=dst_ip))
            src_vm_console.sendline('echo $?')
            src_vm_console.expect('0' if positive else '1')


class TestGuestPerformance(object):
    """
    In-guest performance bandwidth passthrough
    """
    def test_guest_performance(self):
        """
        In-guest performance bandwidth passthrough
        """
        if not pytest.real_nics_env:
            pytest.skip(msg='Only run on bare metal env')

        server_vm = config.VMS_LIST[0]
        client_vm = config.VMS_LIST[1]
        server_ip = config.VMS.get(server_vm).get('ovs_ip')
        with console.Console(vm=server_vm, distro='fedora', namespace=config.NETWORK_NS) as server_vm_console:
            server_vm_console.sendline('iperf3 -sB {server_ip}'.format(server_ip=server_ip))
            with console.Console(vm=client_vm, distro='fedora', namespace=config.NETWORK_NS) as client_vm_console:
                client_vm_console.sendline('iperf3 -c {server_ip} -t 5 -u -J'.format(server_ip=server_ip))
                client_vm_console.expect('}\r\r\n}\r\r\n')
                iperf_data = client_vm_console.before
            server_vm_console.sendline(chr(3))  # Send ctrl+c to kill iperf3 server

        iperf_data += '}\r\r\n}\r\r\n'
        iperf_json = json.loads(iperf_data[iperf_data.find('{'):])
        sum_sent = iperf_json.get('end').get('sum')
        bits_per_second = int(sum_sent.get('bits_per_second'))
        assert float(bitmath.Byte(bits_per_second).GiB) >= 2.5


class TestVethRemovedAfterVmsDeleted(object):
    """
    Check that veth interfaces are removed from host after VM deleted
    """
    def test_veth_removed_from_host_after_vm_deleted(self):
        """
        Check that veth interfaces are removed from host after VM deleted
        """
        for vm in config.VMS_LIST:
            vm_object = VirtualMachine(name=vm, namespace=config.NETWORK_NS)
            vm_info = vm_object.get()
            vm_interfaces = vm_info.get('status', {}).get('interfaces', [])
            vm_node = vm_object.node()
            for pod in pytest.privileged_pods:
                pod_object = Pod(name=pod, namespace=pytest.privileged_pods_ns)
                pod_container = pytest.privileged_pod_container
                pod_node = pod_object.node()
                if pod_node == vm_node:
                    err, out = pod_object.run_command(
                        command=config.IP_LINK_SHOW_BETH_CMD, container=pod_container
                    )
                    assert err
                    host_vath_before_delete = int(out.strip())
                    assert vm_object.delete(wait=True)
                    expect_host_veth = host_vath_before_delete - len(vm_interfaces)

                    sampler = utils.TimeoutSampler(
                        timeout=30, sleep=1, func=get_host_veth_sampler,
                        pod=pod_object, pod_container=pod_container, expect_host_veth=expect_host_veth
                    )
                    sampler.wait_for_func_status(result=True)


@generate_logs()
def get_host_veth_sampler(pod, pod_container, expect_host_veth):
    """
    Wait until host veth are equal to expected veth number

    Args:
        pod (Pod): Pod object.
        pod_container (str): Pod container name.
        expect_host_veth (int): Expected number of veth on the host.

    Returns:
        bool: True if current veth number == expected veth number, False otherwise.
    """
    out = pod.run_command(command=config.IP_LINK_SHOW_BETH_CMD, container=pod_container)[1]
    return int(out.strip()) == expect_host_veth
