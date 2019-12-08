"""
VM to VM connectivity
"""
from ipaddress import ip_interface

import pytest
import tests.network.utils as network_utils
from pytest_testconfig import config as py_config
from tests.network.connectivity import utils
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


@pytest.fixture(scope="module")
def vma(nodes, namespace, unprivileged_client):
    name = "vma"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=nodes[0].name,
        client=unprivileged_client,
        body=fedora_vm_body(name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def vmb(nodes, namespace, unprivileged_client):
    name = "vmb"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=nodes[1].name,
        client=unprivileged_client,
        body=fedora_vm_body(name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def running_vma(vma):
    vma.vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vma.vmi)
    return vma


@pytest.fixture(scope="module")
def running_vmb(vmb):
    vmb.vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmb.vmi)
    return vmb


@pytest.mark.polarion("CNV-2332")
def test_connectivity_over_pod_network(
    skip_when_one_node, vma, vmb, running_vma, running_vmb, namespace
):
    """
    Check connectivity
    """
    network_utils.assert_ping_successful(
        src_vm=running_vma,
        dst_ip=ip_interface(running_vmb.vmi.interfaces[0]["ipAddress"]).ip,
    )


@pytest.mark.xfail(reason="Slow performance on BM, need investigation")
@pytest.mark.polarion("CNV-2334")
def test_guest_performance_over_pod_network(
    skip_not_bare_metal,
    skip_when_one_node,
    vma,
    vmb,
    running_vma,
    running_vmb,
    namespace,
):
    """
    In-guest performance bandwidth passthrough over Linux bridge
    """
    expected_res = py_config["test_guest_performance"]["bandwidth"]
    bits_per_second = utils.run_test_guest_performance(
        server_vm=running_vma,
        client_vm=running_vmb,
        listen_ip=ip_interface(running_vma.vmi.interfaces[0]["ipAddress"]).ip,
    )
    assert bits_per_second >= expected_res
