# -*- coding: utf-8 -*-

import pytest
from resources.utils import TimeoutExpiredError

from utilities.network import LINUX_BRIDGE
from utilities.network import network_device_nocm as network_device
from utilities.network import network_nad_nocm as network_nad
from utilities.virt import VirtualMachineForTests, fedora_vm_body


# todo: revisit the hardcoded value and consolidate it with default timeout
# (perhaps by exposing it via test configuration parameter)
_VM_RUNNING_TIMEOUT = 120  # seems to be enough
_VM_NOT_RUNNING_TIMEOUT = 30
BRIDGEMARKER1 = "bridgemarker1"
BRIDGEMARKER2 = "bridgemarker2"
BRIDGEMARKER3 = "bridgemarker3"


def _get_name(suffix):
    return f"brm-{suffix}"


@pytest.fixture()
def bridgemarker1_nad(namespace):
    attachdef = network_nad(
        nad_type=LINUX_BRIDGE,
        nad_name=BRIDGEMARKER1,
        interface_name=BRIDGEMARKER1,
        namespace=namespace,
    )
    attachdef.deploy()
    yield attachdef
    attachdef.clean_up()


@pytest.fixture()
def bridgemarker2_nad(namespace):
    bridgemarker2_nad = network_nad(
        nad_type=LINUX_BRIDGE,
        nad_name=BRIDGEMARKER2,
        interface_name=BRIDGEMARKER2,
        namespace=namespace,
    )
    bridgemarker2_nad.deploy()
    yield bridgemarker2_nad
    bridgemarker2_nad.clean_up()


@pytest.fixture()
def bridgemarker3_nad(namespace):
    bridgemarker3_nad = network_nad(
        nad_type=LINUX_BRIDGE,
        nad_name=BRIDGEMARKER3,
        interface_name=BRIDGEMARKER3,
        namespace=namespace,
    )
    bridgemarker3_nad.deploy()
    yield bridgemarker3_nad
    bridgemarker3_nad.clean_up()


@pytest.fixture()
def bridge_attached_vmi(namespace, bridgemarker1_nad):
    networks = {bridgemarker1_nad.name: bridgemarker1_nad.name}
    name = _get_name(suffix="bridge-vm")
    vm = VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        networks=networks,
        interfaces=sorted(networks.keys()),
        body=fedora_vm_body(name=name),
    )
    vm.deploy()
    vm.start()
    yield vm.vmi
    vm.clean_up()


@pytest.fixture()
def multi_bridge_attached_vmi(
    namespace, bridgemarker2_nad, bridgemarker3_nad, unprivileged_client
):
    networks = {b.name: b.name for b in (bridgemarker2_nad, bridgemarker3_nad)}
    name = _get_name(suffix="multi-bridge-vm")
    vm = VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        networks=networks,
        interfaces=sorted(networks.keys()),
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
    )
    vm.deploy()
    vm.start()
    yield vm.vmi
    vm.clean_up()


@pytest.fixture()
def bridge_device_on_all_nodes(utility_pods, schedulable_nodes):
    dev = network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="bridge-marker1",
        interface_name=BRIDGEMARKER1,
        network_utility_pods=utility_pods,
        nodes=schedulable_nodes,
    )
    dev.deploy()
    yield dev
    dev.clean_up()


@pytest.fixture()
def bridgemarker2_nncp(skip_when_one_node, utility_pods, worker_node1, worker_node2):
    bridgemarker2_nncp = network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="bridge-marker2",
        interface_name=BRIDGEMARKER2,
        network_utility_pods=utility_pods,
        node_selector=worker_node1.name,
    )
    bridgemarker2_nncp.deploy()
    yield bridgemarker2_nncp
    bridgemarker2_nncp.clean_up()


@pytest.fixture()
def bridgemarker3_nncp(skip_when_one_node, utility_pods, worker_node1, worker_node2):
    bridgemarker3_nncp = network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="bridge-marker3",
        interface_name=BRIDGEMARKER3,
        network_utility_pods=utility_pods,
        node_selector=worker_node2.name,
    )
    bridgemarker3_nncp.deploy()
    yield bridgemarker3_nncp
    bridgemarker3_nncp.clean_up()


def _assert_failure_reason_is_bridge_missing(pod, bridge):
    cond = pod.instance.status.conditions[0]
    missing_resource = bridge.resource_name
    assert cond.reason == "Unschedulable"
    assert f"Insufficient {missing_resource}" in cond.message


@pytest.mark.polarion("CNV-2234")
def test_bridge_marker_no_device(
    skip_rhel7_workers, bridgemarker1_nad, bridge_attached_vmi
):
    """Check that VMI fails to start when bridge device is missing."""
    with pytest.raises(TimeoutExpiredError):
        bridge_attached_vmi.wait_until_running(
            timeout=_VM_NOT_RUNNING_TIMEOUT, logs=False
        )

    # validate the exact reason for VMI startup failure is missing bridge
    pod = bridge_attached_vmi.virt_launcher_pod
    _assert_failure_reason_is_bridge_missing(pod=pod, bridge=bridgemarker1_nad)


# note: the order of fixtures is important because we should first create the
# device before attaching a VMI to it
@pytest.mark.polarion("CNV-2235")
def test_bridge_marker_device_exists(
    skip_rhel7_workers, bridge_device_on_all_nodes, bridge_attached_vmi
):
    """Check that VMI successfully starts when bridge device is present."""
    bridge_attached_vmi.wait_until_running(timeout=_VM_RUNNING_TIMEOUT)


@pytest.mark.polarion("CNV-2309")
def test_bridge_marker_devices_exist_on_different_nodes(
    skip_rhel7_workers,
    bridgemarker2_nad,
    bridgemarker3_nad,
    bridgemarker2_nncp,
    bridgemarker3_nncp,
    multi_bridge_attached_vmi,
):
    """Check that VMI fails to start when attached to two bridges located on different nodes."""
    with pytest.raises(TimeoutExpiredError):
        multi_bridge_attached_vmi.wait_until_running(
            timeout=_VM_NOT_RUNNING_TIMEOUT, logs=False
        )

    # validate the exact reason for VMI startup failure is missing bridge
    pod = multi_bridge_attached_vmi.virt_launcher_pod
    for bridge in (bridgemarker2_nad, bridgemarker3_nad):
        _assert_failure_reason_is_bridge_missing(pod=pod, bridge=bridge)
