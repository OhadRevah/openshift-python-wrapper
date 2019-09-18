"""
VM to VM connectivity
"""
from ipaddress import ip_interface

import pytest
from pytest_testconfig import config as py_config
from tests.network.connectivity import utils
from tests.network.utils import assert_ping_successful
from tests.utils import VirtualMachineForTests, create_ns, wait_for_vm_interfaces


@pytest.fixture(scope="module")
def module_namespace(unprivileged_client):
    yield from create_ns(client=unprivileged_client, name="pod-connectivity")


@pytest.fixture(scope="module")
def vma(nodes, module_namespace, unprivileged_client):
    with VirtualMachineForTests(
        namespace=module_namespace.name,
        name="vma",
        node_selector=nodes[0].name,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.fixture(scope="module")
def vmb(nodes, module_namespace, unprivileged_client):
    with VirtualMachineForTests(
        namespace=module_namespace.name,
        name="vmb",
        node_selector=nodes[1].name,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.fixture(scope="module")
def running_vma(vma):
    wait_for_vm_interfaces(vmi=vma.vmi)
    return vma


@pytest.fixture(scope="module")
def running_vmb(vmb):
    wait_for_vm_interfaces(vmi=vmb.vmi)
    return vmb


@pytest.mark.polarion("CNV-2332")
def test_connectivity_over_pod_network(
    skip_when_one_node, vma, vmb, running_vma, running_vmb, module_namespace
):
    """
    Check connectivity
    """
    assert_ping_successful(
        src_vm=running_vma,
        dst_ip=ip_interface(running_vmb.vmi.interfaces[0]["ipAddress"]).ip,
    )


@pytest.mark.skipif(not py_config["bare_metal_cluster"], reason="virtualized cluster")
@pytest.mark.xfail(reason="Slow performance on BM, need investigation")
@pytest.mark.polarion("CNV-2334")
def test_guest_performance_over_pod_network(
    skip_when_one_node, vma, vmb, running_vma, running_vmb, module_namespace
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
