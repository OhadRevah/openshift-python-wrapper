# -*- coding: utf-8 -*-

import pytest
from pytest_testconfig import config as py_config

from resources import network_attachment_definition as nad
from resources.namespace import Namespace
from resources.virtual_machine_instance import VirtualMachineInstance

from tests.network import utils

_RESOURCE_NAME_PREFIX = "brm-"

# todo: revisit the hardcoded value and consolidate it with default timeout
# (perhaps by exposing it via test configuration parameter)
_VM_RUNNING_TIMEOUT = 60  # seems to be enough


def _get_name(suffix):
    return _RESOURCE_NAME_PREFIX + suffix


def _get_bridge_name():
    return _get_name("br")


def _get_network_attachment_name():
    return _get_name("nad")


@pytest.fixture()
def namespace():
    with Namespace(name=_get_name("ns")) as ns:
        yield ns


@pytest.fixture()
def bridge_network(namespace):
    cni_type = py_config['template_defaults']['bridge_cni_name']
    with nad.BridgeNetworkAttachmentDefinition(
            namespace=namespace.name,
            name=_get_network_attachment_name(),
            bridge_name=_get_bridge_name(),
            cni_type=cni_type) as attachdef:
        yield attachdef


class VirtualMachineInstanceAttachedToBridge(VirtualMachineInstance):
    def _to_dict(self):
        res = super()._to_dict()

        # add a default network if attaching to other networks
        res["spec"]["networks"] = [{
            "name": "default",
            "pod": {},
        }]
        res["spec"]["domain"]["devices"]["interfaces"] = [{
            "name": "default",
            "bridge": {},
        }]

        # also attach to bridge network
        network_name = "net1"
        res["spec"]["networks"].append({
            "name": network_name,
            "multus": {
                "networkName": _get_network_attachment_name(),
            },
        })
        res["spec"]["domain"]["devices"]["interfaces"].append({
            "name": network_name,
            "bridge": {},
        })

        return res


@pytest.fixture()
def bridge_attached_vmi(namespace, bridge_network):
    with VirtualMachineInstanceAttachedToBridge(
            namespace=namespace.name,
            name=_get_name("vmi")) as vmi:
        yield vmi


@pytest.fixture()
def bridge_device(network_utility_pods):
    with utils.Bridge(
            name=_get_bridge_name(), worker_pods=network_utility_pods) as dev:
        yield from dev


@pytest.mark.polarion("CNV-2234")
def test_bridge_marker_no_device(bridge_attached_vmi):
    """Check that VMI fails to start when bridge device is missing."""
    assert not bridge_attached_vmi.wait_until_running(timeout=_VM_RUNNING_TIMEOUT)

    # validate the exact reason for VMI startup failure is missing bridge
    pod = bridge_attached_vmi.virt_launcher_pod()
    message = pod.instance.status.conditions[0].message
    missing_resource = nad.get_resource_name(_get_bridge_name())
    assert pod.instance.status.conditions[0].reason == "Unschedulable"
    assert f"Insufficient {missing_resource}" in message


# note: the order of fixtures is important because we should first create the
# device before attaching a VMI to it
@pytest.mark.polarion("CNV-2235")
def test_bridge_marker_device_exists(bridge_device, bridge_attached_vmi):
    """Check that VMI successfully starts when bridge device is present."""
    assert bridge_attached_vmi.wait_until_running(timeout=_VM_RUNNING_TIMEOUT)
