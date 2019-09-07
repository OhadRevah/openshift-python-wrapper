import pytest

import tests.network.utils as network_utils
from tests import utils
from resources.namespace import Namespace
from resources.network_addons_config import NetworkAddonsConfig

LINUX_BRIDGE_NAME = "br1test"


@pytest.fixture(scope="module", autouse="True")
def module_namespace():
    with Namespace(name="test-network-operator") as ns:
        yield ns


@pytest.fixture(scope="module", autouse="True")
def bridge_device(network_utility_pods):
    with utils.Bridge(
        name=LINUX_BRIDGE_NAME, worker_pods=network_utility_pods
    ) as br_dev:
        yield br_dev


@pytest.fixture(scope="module", autouse="True")
def br1test_nad(module_namespace):
    with network_utils.linux_bridge_nad(
        namespace=module_namespace, name=LINUX_BRIDGE_NAME, bridge=LINUX_BRIDGE_NAME
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def network_addons_config_cr(default_client):
    nac = NetworkAddonsConfig.get(
        default_client, label_selector="app=hyperconverged-cluster"
    )
    nac_list = list(nac)
    assert nac_list, "There should be one NetworkAddonsConfig CR."
    yield nac_list[0]


@pytest.fixture(scope="module", autouse="True")
def bridge_attached_vm(module_namespace):

    with utils.TestVirtualMachine(
        namespace=module_namespace.name,
        interfaces=[LINUX_BRIDGE_NAME],
        networks={LINUX_BRIDGE_NAME: LINUX_BRIDGE_NAME},
        name="oper-test-vm",
    ) as vm:
        vm.start()
        yield vm


@pytest.mark.polarion("CNV-2520")
def test_component_installed_by_operator(network_addons_config_cr):
    """
    Verify that the network addons operator is supposed to install Linux-Bridge
    (a mandatory default component), by checking if the component appears in
    the operator CR.
    """
    component_name_in_cr = "linuxBridge"
    assert (
        component_name_in_cr in network_addons_config_cr.instance.spec.keys()
    ), f"{component_name_in_cr} is missing from the network operator CR."


@pytest.mark.polarion("CNV-2296")
def test_linux_bridge_functionality(bridge_attached_vm):
    """
    Verify the linux-bridge component valid functionality.
    Start a VM and verify it starts successfully, as an indication of successful
    deployment of linux-bridge.
    """
    bridge_attached_vm.vmi.wait_until_running()
