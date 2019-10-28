import pytest
import tests.network.utils as network_utils
from resources.network_addons_config import NetworkAddonsConfig
from utilities.network import LinuxBridgeNodeNetworkConfigurationPolicy
from utilities.virt import VirtualMachineForTests, fedora_vm_body


@pytest.fixture(scope="module", autouse="True")
def bridge_device(network_utility_pods):
    with LinuxBridgeNodeNetworkConfigurationPolicy(
        name="test-network-operator",
        bridge_name="br1test",
        worker_pods=network_utility_pods,
    ) as br_dev:
        yield br_dev


@pytest.fixture(scope="module", autouse="True")
def br1test_nad(namespace, bridge_device):
    with network_utils.linux_bridge_nad(
        namespace=namespace,
        name=bridge_device.bridge_name,
        bridge=bridge_device.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def network_addons_config_cr(default_client):
    nac = NetworkAddonsConfig.get(default_client)
    nac_list = list(nac)
    assert nac_list, "There should be one NetworkAddonsConfig CR."
    yield nac_list[0]


@pytest.fixture(scope="module")
def bridge_attached_vm(namespace, br1test_nad):
    name = "oper-test-vm"
    with VirtualMachineForTests(
        namespace=namespace.name,
        interfaces=[br1test_nad.name],
        networks={br1test_nad.name: br1test_nad.name},
        name=name,
        body=fedora_vm_body(name),
    ) as vm:
        vm.start(wait=True)
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
