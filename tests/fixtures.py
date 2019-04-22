# -*- coding: utf-8 -*-

"""
Pytest fixtures file for CNV tests
"""

import logging

import pytest

from resources.resource import NamespacedResource
from resources.virtual_machine import VirtualMachine
from resources.virtual_machine_instance import VirtualMachineInstance
from tests import utils as test_utils
from tests.utils import wait_for_vm_interfaces
from utilities import utils

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope='class')
def create_resources_from_yaml(request):
    """
    Create resources from yamls
    """
    namespace = test_utils.get_fixture_val(request=request, attr_name="namespace")
    yamls = test_utils.get_fixture_val(request=request, attr_name="yamls")
    resource = NamespacedResource(namespace=namespace)

    def fin():
        """
        Remove resources from yamls
        """
        for yaml_ in yamls:
            resource.delete(yaml_file=yaml_)
    request.addfinalizer(fin)

    for yaml_ in yamls:
        resource.create(yaml_file=yaml_, wait=True)


@pytest.fixture(scope='class')
def create_vms_from_template(request):
    """
    Create VMs

    template_kwargs are the params that sent to the template.
    For example to create a CM with name fedora-vm-1 and 512Mi memory set
    template_kwargs = {
        "NAME": "fedora-vm-1",
        "MEMORY": "512Mi"
        }

    To create a VM named vm-fedora-1 with cloud-init data and 4 interfaces with IPs send:
    VM = {
    "vm-fedora-1": {
        "cloud_init": {
            "bootcmd": ["dnf install -y iperf3 qemu-guest-agent"],
            "runcmd": ["systemctl start qemu-guest-agent"]
            },
        "interfaces": {
            BRIDGE_BR1: ["192.168.0.1"],
            BRIDGE_BR1VLAN100: ["192.168.1.1"],
            BRIDGE_BR1VLAN200: ["192.168.2.1"],
            },
        "bonds": {
            BRIDGE_BR1BOND: ["192.168.3.1"],
            }
        }
    }

    """
    vms = test_utils.get_fixture_val(request=request, attr_name="vms")
    template = test_utils.get_fixture_val(request=request, attr_name="template")
    namespace = test_utils.get_fixture_val(request=request, attr_name="namespace")
    nmcli_add_con = "nmcli con add type ethernet con-name"
    template_kwargs = test_utils.get_fixture_val(
        request=request, attr_name="template_kwargs", default_value={}
    )

    def fin():
        """
        Remove created VMs if exists (TestVethRemovedAfterVmsDeleted should remove them)
        """
        for vm in vms:
            vm_object = VirtualMachine(name=vm, namespace=namespace)
            if vm_object.get():
                vm_object.delete(wait=True)
    request.addfinalizer(fin)

    for name, info in vms.items():
        vm_object = VirtualMachine(name=name, namespace=namespace)
        boot_cmd = info.get("cloud_init", {}).get("bootcmd")
        run_cmd = info.get("cloud_init", {}).get("runcmd")
        json_out = utils.get_json_from_template(
            file_=template, NAME=name, **template_kwargs
        )
        spec = json_out.get('spec').get('template').get('spec')
        vm_metadata = info.get("metadata")
        if vm_metadata:
            json_out['spec']['template']['metadata'].update(vm_metadata)

        interfaces = spec.get('domain').get('devices').get('interfaces')
        networks = spec.get('networks')
        for interface in info.get("interfaces", []):
            if interface == "pod":
                continue

            interfaces.append({'bridge': {}, 'name': interface})
            networks.append({'multus': {'networkName': interface}, 'name': interface})

        if pytest.bond_support_env:
            for bond in info.get("bonds", []):
                interfaces.append({'bridge': {}, 'name': bond})
                networks.append({'multus': {'networkName': bond}, 'name': bond})

        spec['domain']['devices']['interfaces'] = interfaces
        spec['networks'] = networks

        volumes = spec.get('volumes')
        cloud_init = [i for i in volumes if 'cloudInitNoCloud' in i][0]
        cloud_init_data = volumes.pop(volumes.index(cloud_init))
        cloud_init_user_data = cloud_init_data.get('cloudInitNoCloud').get('userData')
        if boot_cmd:
            cloud_init_user_data += "\nbootcmd:\n"
            for cmd in boot_cmd:
                cloud_init_user_data += f"  - {cmd}\n"

        if run_cmd:
            cloud_init_user_data += "\nruncmd:\n"
            for cmd in run_cmd:
                cloud_init_user_data += f"  - {cmd}\n"

        if cloud_init_user_data and "runcmd" not in cloud_init_user_data:
            cloud_init_user_data += "\nruncmd:\n"

        idx = 1
        all_interfaces = []
        for interface_name, ips in info.get("interfaces", {}).items():
            eth_name = f"eth{idx}"
            all_interfaces.append(eth_name)
            cloud_init_user_data += f"  - {nmcli_add_con} {eth_name} ifname {eth_name}\n"
            for ip in ips:
                cloud_init_user_data += f"  - nmcli con mod {eth_name} ipv4.addresses {ip}/24 ipv4.method manual\n"

            idx += 1

        if pytest.bond_support_env:
            for bond_name, ips in info.get("bonds", {}).items():
                eth_name = f"eth{idx}"
                all_interfaces.append(eth_name)
                cloud_init_user_data += f"  - {nmcli_add_con} {eth_name} ifname {eth_name}\n"
                for ip in ips:
                    cloud_init_user_data += f"  - nmcli con mod {eth_name} ipv4.addresses {ip}/24 ipv4.method manual\n"

                idx += 1

        if not pytest.real_nics_env:
            for eth in all_interfaces:
                cloud_init_user_data += f"  - ip link set mtu 1450 {eth}\n"

        cloud_init_data['cloudInitNoCloud']['userData'] = cloud_init_user_data
        volumes.append(cloud_init_data)
        spec['volumes'] = volumes
        json_out['spec']['template']['spec'] = spec
        assert vm_object.create(resource_dict=json_out, wait=True)


@pytest.fixture(scope='class')
def wait_for_vms_running(request):
    """
    Wait until VMs in status Running
    """
    vms = test_utils.get_fixture_val(request=request, attr_name="vms")
    namespace = test_utils.get_fixture_val(request=request, attr_name="namespace")
    for vmi in vms:
        vmi_object = VirtualMachineInstance(name=vmi, namespace=namespace)
        assert vmi_object.running()


@pytest.fixture(scope='class')
def wait_for_vms_interfaces_report(request):
    """
    Wait until VMs report guest agant data
    """
    vms = test_utils.get_fixture_val(request=request, attr_name="vms")
    namespace = test_utils.get_fixture_val(request=request, attr_name="namespace")
    for vmi in vms:
        vmi_object = VirtualMachineInstance(name=vmi, namespace=namespace)
        wait_for_vm_interfaces(vmi=vmi_object, timeout=720)
