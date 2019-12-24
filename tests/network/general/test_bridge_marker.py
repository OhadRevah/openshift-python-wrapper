# -*- coding: utf-8 -*-
import time

import pytest
from resources.utils import TimeoutExpiredError
from tests.network import utils as network_utils
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
def bridge_network(namespace):
    with network_utils.bridge_nad(
        nad_type=network_utils.LINUX_BRIDGE,
        nad_name=BRIDGEMARKER1,
        bridge_name=BRIDGEMARKER1,
        namespace=namespace,
    ) as attachdef:
        yield attachdef


@pytest.fixture()
def bridge_networks(namespace):
    with network_utils.bridge_nad(
        nad_type=network_utils.LINUX_BRIDGE,
        nad_name=BRIDGEMARKER2,
        bridge_name=BRIDGEMARKER2,
        namespace=namespace,
    ) as bridgemarker2_nad:
        with network_utils.bridge_nad(
            nad_type=network_utils.LINUX_BRIDGE,
            nad_name=BRIDGEMARKER3,
            bridge_name=BRIDGEMARKER3,
            namespace=namespace,
        ) as bridgemarker3_nad:
            yield (bridgemarker2_nad, bridgemarker3_nad)


@pytest.fixture()
def bridge_attached_vmi(namespace, bridge_network):
    networks = {bridge_network.name: bridge_network.name}
    name = _get_name(f"bridge-vm-{time.time()}")
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        networks=networks,
        interfaces=sorted(networks.keys()),
        body=fedora_vm_body(name),
    ) as vm:
        vm.start()
        yield vm.vmi


@pytest.fixture()
def multi_bridge_attached_vmi(namespace, bridge_networks, unprivileged_client):
    networks = {b.name: b.name for b in bridge_networks}
    name = _get_name(f"multi-bridge-vm-{time.time()}")
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        networks=networks,
        interfaces=sorted(networks.keys()),
        client=unprivileged_client,
        body=fedora_vm_body(name),
    ) as vm:
        vm.start()
        yield vm.vmi


@pytest.fixture()
def bridge_device_on_all_nodes(network_utility_pods, nodes):
    with network_utils.bridge_device(
        bridge_type=network_utils.LINUX_BRIDGE,
        nncp_name="bridge-marker1",
        bridge_name=BRIDGEMARKER1,
        network_utility_pods=network_utility_pods,
        nodes=nodes,
        vxlan=False,
    ) as dev:
        yield dev


@pytest.fixture()
def non_homogenous_bridges(skip_when_one_node, network_utility_pods, nodes):
    with network_utils.bridge_device(
        bridge_type=network_utils.LINUX_BRIDGE,
        nncp_name="bridge-marker2",
        bridge_name=BRIDGEMARKER2,
        network_utility_pods=[network_utility_pods[0]],
        nodes=nodes,
        node_selector=network_utility_pods[0].node.name,
        vxlan=False,
    ) as bridgemarker2_ncp:
        with network_utils.bridge_device(
            bridge_type=network_utils.LINUX_BRIDGE,
            nncp_name="bridge-marker3",
            bridge_name=BRIDGEMARKER3,
            network_utility_pods=[network_utility_pods[1]],
            nodes=nodes,
            node_selector=network_utility_pods[1].node.name,
            vxlan=False,
        ) as bridgemarker3_ncp:
            yield (bridgemarker2_ncp, bridgemarker3_ncp)


def _assert_failure_reason_is_bridge_missing(pod, bridge):
    cond = pod.instance.status.conditions[0]
    missing_resource = bridge.resource_name
    assert cond.reason == "Unschedulable"
    assert f"Insufficient {missing_resource}" in cond.message


@pytest.mark.polarion("CNV-2234")
def test_bridge_marker_no_device(bridge_network, bridge_attached_vmi):
    """Check that VMI fails to start when bridge device is missing."""
    with pytest.raises(TimeoutExpiredError):
        bridge_attached_vmi.wait_until_running(
            timeout=_VM_NOT_RUNNING_TIMEOUT, logs=False
        )

    # validate the exact reason for VMI startup failure is missing bridge
    pod = bridge_attached_vmi.virt_launcher_pod
    _assert_failure_reason_is_bridge_missing(pod, bridge_network)


# note: the order of fixtures is important because we should first create the
# device before attaching a VMI to it
@pytest.mark.polarion("CNV-2235")
def test_bridge_marker_device_exists(bridge_device_on_all_nodes, bridge_attached_vmi):
    """Check that VMI successfully starts when bridge device is present."""
    bridge_attached_vmi.wait_until_running(timeout=_VM_RUNNING_TIMEOUT)


@pytest.mark.polarion("CNV-2309")
def test_bridge_marker_devices_exist_on_different_nodes(
    bridge_networks, non_homogenous_bridges, multi_bridge_attached_vmi
):
    """Check that VMI fails to start when attached to two bridges located on different nodes."""
    with pytest.raises(TimeoutExpiredError):
        multi_bridge_attached_vmi.wait_until_running(
            timeout=_VM_NOT_RUNNING_TIMEOUT, logs=False
        )

    # validate the exact reason for VMI startup failure is missing bridge
    pod = multi_bridge_attached_vmi.virt_launcher_pod
    for bridge in bridge_networks:
        _assert_failure_reason_is_bridge_missing(pod, bridge)
