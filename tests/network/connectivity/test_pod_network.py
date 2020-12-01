"""
VM to VM connectivity
"""
from ipaddress import ip_interface

import pytest
from pytest_testconfig import config as py_config

import utilities.network
from tests.network.connectivity import utils
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


@pytest.fixture(scope="module")
def pod_net_vma(
    worker_node1,
    namespace,
    unprivileged_client,
    nic_models_matrix__module__,
):
    name = "vma"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=worker_node1.name,
        client=unprivileged_client,
        network_model=nic_models_matrix__module__,
        body=fedora_vm_body(name=name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def pod_net_vmb(
    worker_node2,
    namespace,
    unprivileged_client,
    nic_models_matrix__module__,
):
    name = "vmb"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=worker_node2.name,
        client=unprivileged_client,
        network_model=nic_models_matrix__module__,
        body=fedora_vm_body(name=name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def pod_net_running_vma(pod_net_vma):
    pod_net_vma.vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=pod_net_vma.vmi)
    return pod_net_vma


@pytest.fixture(scope="module")
def pod_net_running_vmb(pod_net_vmb):
    pod_net_vmb.vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=pod_net_vmb.vmi)
    return pod_net_vmb


@pytest.mark.polarion("CNV-2332")
def test_connectivity_over_pod_network(
    skip_when_one_node,
    skip_rhel7_workers,
    pod_net_vma,
    pod_net_vmb,
    pod_net_running_vma,
    pod_net_running_vmb,
    namespace,
):
    """
    Check connectivity
    """
    utilities.network.assert_ping_successful(
        src_vm=pod_net_running_vma,
        dst_ip=ip_interface(pod_net_running_vmb.vmi.interfaces[0]["ipAddress"]).ip,
    )


@pytest.mark.xfail(reason="Slow performance on BM, need investigation")
@pytest.mark.polarion("CNV-2334")
def test_guest_performance_over_pod_network(
    skip_if_workers_vms,
    skip_when_one_node,
    skip_rhel7_workers,
    pod_net_vma,
    pod_net_vmb,
    pod_net_running_vma,
    pod_net_running_vmb,
    namespace,
):
    """
    In-guest performance bandwidth passthrough over Linux bridge
    """
    expected_res = py_config["test_guest_performance"]["bandwidth"]
    bits_per_second = utils.run_test_guest_performance(
        server_vm=pod_net_running_vma,
        client_vm=pod_net_running_vmb,
        listen_ip=ip_interface(pod_net_running_vma.vmi.interfaces[0]["ipAddress"]).ip,
    )
    assert bits_per_second >= expected_res
