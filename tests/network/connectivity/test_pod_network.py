"""
VM to VM connectivity
"""
from ipaddress import ip_interface

import pytest
from pytest_testconfig import config as py_config

from tests.network.utils import run_test_guest_performance
from utilities.constants import IPV6_STR
from utilities.network import (
    assert_ping_successful,
    compose_cloud_init_data_dict,
    get_ip_from_vm_or_virt_handler_pod,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


@pytest.fixture()
def pod_net_vma(
    skip_ipv6_if_not_dual_stack_cluster,
    worker_node1,
    namespace,
    unprivileged_client,
    nic_models_matrix__module__,
    cloud_init_ipv6_network_data,
):
    name = "vma"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=worker_node1.name,
        client=unprivileged_client,
        network_model=nic_models_matrix__module__,
        body=fedora_vm_body(name=name),
        cloud_init_data=cloud_init_ipv6_network_data,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture()
def pod_net_vmb(
    skip_ipv6_if_not_dual_stack_cluster,
    worker_node2,
    namespace,
    unprivileged_client,
    nic_models_matrix__module__,
    cloud_init_ipv6_network_data,
):
    name = "vmb"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=worker_node2.name,
        client=unprivileged_client,
        network_model=nic_models_matrix__module__,
        body=fedora_vm_body(name=name),
        cloud_init_data=cloud_init_ipv6_network_data,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture()
def pod_net_running_vma(pod_net_vma):
    return running_vm(vm=pod_net_vma)


@pytest.fixture()
def pod_net_running_vmb(pod_net_vmb):
    return running_vm(vm=pod_net_vmb)


@pytest.fixture(scope="module")
def cloud_init_ipv6_network_data(dual_stack_network_data):
    return compose_cloud_init_data_dict(ipv6_network_data=dual_stack_network_data)


@pytest.mark.polarion("CNV-2332")
def test_connectivity_over_pod_network(
    ip_stack_version_matrix__module__,
    skip_when_one_node,
    pod_net_vma,
    pod_net_vmb,
    pod_net_running_vma,
    pod_net_running_vmb,
    namespace,
):
    """
    Check connectivity
    """
    if ip_stack_version_matrix__module__ == IPV6_STR:
        dst_ip = get_ip_from_vm_or_virt_handler_pod(
            family=IPV6_STR, vm=pod_net_running_vmb
        )
        assert (
            dst_ip
        ), f"Cannot get valid IPv6 address from {pod_net_running_vmb.vmi.name}."

    else:
        dst_ip = ip_interface(
            address=pod_net_running_vmb.vmi.interfaces[0]["ipAddress"]
        ).ip

    assert_ping_successful(
        src_vm=pod_net_running_vma,
        dst_ip=dst_ip,
    )


@pytest.mark.polarion("CNV-2334")
def test_guest_performance_over_pod_network(
    skip_if_workers_vms,
    skip_when_one_node,
    pod_net_vma,
    pod_net_vmb,
    pod_net_running_vma,
    pod_net_running_vmb,
):
    """
    In-guest performance bandwidth passthrough over Linux bridge
    """
    expected_res = py_config["test_guest_performance"]["bandwidth"]
    bits_per_second = run_test_guest_performance(
        server_vm=pod_net_running_vma,
        client_vm=pod_net_running_vmb,
        target_ip=ip_interface(pod_net_running_vma.vmi.interfaces[0]["ipAddress"]).ip,
    )

    assert bits_per_second >= expected_res
