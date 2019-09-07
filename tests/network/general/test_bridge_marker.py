# -*- coding: utf-8 -*-

import time

import pytest
from pytest_testconfig import config as py_config

from tests import utils
from resources import network_attachment_definition as nad
from resources.namespace import Namespace
from resources.utils import TimeoutExpiredError
from tests.network import utils as network_utils

# todo: revisit the hardcoded value and consolidate it with default timeout
# (perhaps by exposing it via test configuration parameter)
_VM_RUNNING_TIMEOUT = 120  # seems to be enough


def _get_name(suffix):
    return f"brm-{suffix}"


@pytest.fixture(scope="module")
def namespace():
    with Namespace(name=_get_name("ns")) as ns:
        yield ns


@pytest.fixture()
def bridge_network(namespace):
    cni_type = py_config["template_defaults"]["linux_bridge_cni_name"]
    with nad.LinuxBridgeNetworkAttachmentDefinition(
        namespace=namespace.name, name="redbr", bridge_name="redbr", cni_type=cni_type
    ) as attachdef:
        yield attachdef


@pytest.fixture()
def bridge_networks(namespace):
    with network_utils.linux_bridge_nad(namespace, "redbr", "redbr") as rednad:
        with network_utils.linux_bridge_nad(namespace, "bluebr", "bluebr") as bluenad:
            yield (rednad, bluenad)


@pytest.fixture()
def bridge_attached_vmi(namespace, bridge_network):
    networks = {bridge_network.name: bridge_network.name}
    with utils.TestVirtualMachine(
        namespace=namespace.name,
        name=_get_name(f"bridge-vm-{time.time()}"),
        networks=networks,
        interfaces=sorted(networks.keys()),
    ) as vm:
        vm.start()
        yield vm.vmi


@pytest.fixture()
def multi_bridge_attached_vmi(namespace, bridge_networks):
    networks = {b.name: b.name for b in bridge_networks}
    with utils.TestVirtualMachine(
        namespace=namespace.name,
        name=_get_name(f"multi-bridge-vm-{time.time()}"),
        networks=networks,
        interfaces=sorted(networks.keys()),
    ) as vm:
        vm.start()
        yield vm.vmi


@pytest.fixture()
def bridge_device_on_all_nodes(network_utility_pods):
    with utils.Bridge(name="redbr", worker_pods=network_utility_pods) as dev:
        yield dev


@pytest.fixture()
def non_homogenous_bridges(skip_when_one_node, network_utility_pods):
    with utils.Bridge(name="redbr", worker_pods=[network_utility_pods[0]]) as redbr:
        with utils.Bridge(
            name="bluebr", worker_pods=[network_utility_pods[1]]
        ) as bluebr:
            yield (redbr, bluebr)


def _assert_failure_reason_is_bridge_missing(pod, bridge_name):
    cond = pod.instance.status.conditions[0]
    missing_resource = nad.get_resource_name(bridge_name)
    assert cond.reason == "Unschedulable"
    assert f"Insufficient {missing_resource}" in cond.message


@pytest.mark.polarion("CNV-2234")
def test_bridge_marker_no_device(bridge_attached_vmi):
    """Check that VMI fails to start when bridge device is missing."""
    with pytest.raises(TimeoutExpiredError):
        bridge_attached_vmi.wait_until_running(timeout=_VM_RUNNING_TIMEOUT, logs=False)

    # validate the exact reason for VMI startup failure is missing bridge
    pod = bridge_attached_vmi.virt_launcher_pod
    _assert_failure_reason_is_bridge_missing(pod, "redbr")


# note: the order of fixtures is important because we should first create the
# device before attaching a VMI to it
@pytest.mark.polarion("CNV-2235")
def test_bridge_marker_device_exists(bridge_device_on_all_nodes, bridge_attached_vmi):
    """Check that VMI successfully starts when bridge device is present."""
    bridge_attached_vmi.wait_until_running(timeout=_VM_RUNNING_TIMEOUT)


@pytest.mark.polarion("CNV-2309")
def test_bridge_marker_devices_exist_on_different_nodes(
    non_homogenous_bridges, multi_bridge_attached_vmi
):
    """Check that VMI fails to start when attached to two bridges located on different nodes."""
    with pytest.raises(TimeoutExpiredError):
        multi_bridge_attached_vmi.wait_until_running(
            timeout=_VM_RUNNING_TIMEOUT, logs=False
        )

    # validate the exact reason for VMI startup failure is missing bridge
    pod = multi_bridge_attached_vmi.virt_launcher_pod
    for bridge in non_homogenous_bridges:
        _assert_failure_reason_is_bridge_missing(pod, bridge.name)
