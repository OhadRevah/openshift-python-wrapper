import pytest

from utilities.network import LINUX_BRIDGE
from utilities.network import network_device_nocm as network_device
from utilities.network import network_nad_nocm as network_nad
from utilities.virt import VirtualMachineForTests, fedora_vm_body


@pytest.fixture(scope="module")
def net_add_op_bridge_device(utility_pods, worker_node1):
    br_dev = network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="test-network-operator",
        interface_name="br1test",
        network_utility_pods=utility_pods,
        node_selector=worker_node1.name,
    )
    br_dev.deploy()
    yield br_dev
    br_dev.clean_up()


@pytest.fixture(scope="module")
def net_add_op_br1test_nad(namespace, net_add_op_bridge_device):
    nad = network_nad(
        nad_type=LINUX_BRIDGE,
        nad_name=net_add_op_bridge_device.bridge_name,
        interface_name=net_add_op_bridge_device.bridge_name,
        namespace=namespace,
    )
    nad.deploy()
    yield nad
    nad.clean_up()


@pytest.fixture(scope="module")
def net_add_op_bridge_attached_vm(namespace, net_add_op_br1test_nad):
    name = "oper-test-vm"
    vm = VirtualMachineForTests(
        namespace=namespace.name,
        interfaces=[net_add_op_br1test_nad.name],
        networks={net_add_op_br1test_nad.name: net_add_op_br1test_nad.name},
        name=name,
        body=fedora_vm_body(name=name),
    )
    vm.deploy()
    vm.start(wait=True)
    yield vm
    vm.clean_up()


@pytest.mark.ci
@pytest.mark.polarion("CNV-2520")
def test_component_installed_by_operator(skip_rhel7_workers, network_addons_config):
    """
    Verify that the network addons operator is supposed to install Linux-Bridge
    (a mandatory default component), by checking if the component appears in
    the operator CR.
    """
    component_name_in_cr = "linuxBridge"
    assert (
        component_name_in_cr in network_addons_config.instance.spec.keys()
    ), f"{component_name_in_cr} is missing from the network operator CR."


@pytest.mark.ci
@pytest.mark.polarion("CNV-2296")
def test_linux_bridge_functionality(skip_rhel7_workers, net_add_op_bridge_attached_vm):
    """
    Verify the linux-bridge component valid functionality.
    Start a VM and verify it starts successfully, as an indication of successful
    deployment of linux-bridge.
    """
    net_add_op_bridge_attached_vm.vmi.wait_until_running()
