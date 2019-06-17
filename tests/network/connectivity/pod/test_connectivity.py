"""
VM to VM connectivity
"""
from ipaddress import ip_interface

import pytest
from pytest_testconfig import config as py_config

from resources.namespace import Namespace
from tests.network.connectivity import utils
from tests.network.utils import run_test_connectivity
from tests.utils import wait_for_vm_interfaces, FedoraVirtualMachine

CLOUD_INIT_USER_DATA = r'''
            #cloud-config
            password: fedora
            chpasswd: { expire: False }
            bootcmd:
              - dnf install -y iperf3 qemu-guest-agent
            runcmd:
              - systemctl start qemu-guest-agent'''


class VirtualMachineAttachedToBridge(FedoraVirtualMachine):
    def __init__(
        self, name, namespace, interfaces=None, networks=None, cloud_init_user_data=None, **vm_attr
    ):
        super().__init__(
            name=name,
            namespace=namespace,
            interfaces=interfaces,
            networks=networks,
            cloud_init_user_data=cloud_init_user_data,
            **vm_attr
        )


@pytest.fixture(scope='module', autouse=True)
def module_namespace():
    with Namespace(name='pod-connectivity') as ns:
        yield ns


@pytest.fixture(scope='module')
def vma(module_namespace):
    with VirtualMachineAttachedToBridge(
        namespace=module_namespace.name, name='vma', cloud_init_user_data=CLOUD_INIT_USER_DATA
    ) as vm:
        assert vm.start()
        yield vm


@pytest.fixture(scope='module')
def vmb(module_namespace):
    with VirtualMachineAttachedToBridge(
        namespace=module_namespace.name, name='vmb', cloud_init_user_data=CLOUD_INIT_USER_DATA
    ) as vm:
        assert vm.start()
        yield vm


@pytest.fixture(scope='module')
def running_vma(vma):
    assert wait_for_vm_interfaces(vmi=vma.vmi, timeout=720)
    return vma


@pytest.fixture(scope='module')
def running_vmb(vmb):
    assert wait_for_vm_interfaces(vmi=vmb.vmi, timeout=720)
    return vmb


@pytest.mark.polarion('CNV-2332')
def test_connectivity_over_pod_network(vma, vmb, running_vma, running_vmb, module_namespace):
    """
    Check connectivity
    """
    run_test_connectivity(
        src_vm=running_vma.name,
        dst_vm=running_vmb.name,
        dst_ip=ip_interface(running_vma.vmi.interfaces[0]['ipAddress']).ip,
        positive=True,
        namespace=module_namespace.name
    )


@pytest.mark.skipif(not py_config['bare_metal_cluster'], reason='virtualized cluster')
@pytest.mark.xfail(reason='Slow performance on BM, need investigation')
@pytest.mark.polarion('CNV-2334')
def test_guest_performance_over_pod_network(
    vma,
    vmb,
    running_vma,
    running_vmb,
    module_namespace
):
    """
    In-guest performance bandwidth passthrough over Linux bridge
    """
    expected_res = py_config['test_guest_performance']['bandwidth']
    bits_per_second = utils.run_test_guest_performance(
        server_vm=running_vma.name,
        client_vm=running_vmb.name,
        listen_ip=ip_interface(running_vma.vmi.interfaces[0]['ipAddress']).ip,
        namespace=module_namespace.name
    )
    assert bits_per_second >= expected_res
