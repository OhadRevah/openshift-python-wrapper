import pytest

from utilities.network import LINUX_BRIDGE, cloud_init, network_nad
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


NAD_MAC_SPOOF_NAME = "brspoofupgrade"


@pytest.fixture(scope="session")
def upgrade_linux_macspoof_nad(
    upgrade_namespace_scope_session,
):
    with network_nad(
        namespace=upgrade_namespace_scope_session,
        nad_type=LINUX_BRIDGE,
        nad_name=NAD_MAC_SPOOF_NAME,
        interface_name=NAD_MAC_SPOOF_NAME,
        macspoofchk=True,
        add_resource_name=False,
    ) as nad:
        yield nad


@pytest.fixture(scope="session")
def vm_nad_networks_data(upgrade_linux_macspoof_nad):
    return {upgrade_linux_macspoof_nad.name: upgrade_linux_macspoof_nad.name}


@pytest.fixture(scope="session")
def vma_upgrade_mac_spoof(
    worker_node1, unprivileged_client, upgrade_linux_macspoof_nad, vm_nad_networks_data
):
    name = "vma-macspoof"
    with VirtualMachineForTests(
        name=name,
        namespace=upgrade_linux_macspoof_nad.namespace,
        networks=vm_nad_networks_data,
        interfaces=sorted(vm_nad_networks_data.keys()),
        client=unprivileged_client,
        cloud_init_data=cloud_init(ip_address="10.200.0.1"),
        body=fedora_vm_body(name=name),
        node_selector=worker_node1.hostname,
        running=True,
    ) as vm:
        yield vm


@pytest.fixture(scope="session")
def vmb_upgrade_mac_spoof(
    worker_node1, unprivileged_client, upgrade_linux_macspoof_nad, vm_nad_networks_data
):
    name = "vmb-macspoof"
    with VirtualMachineForTests(
        name=name,
        namespace=upgrade_linux_macspoof_nad.namespace,
        networks=vm_nad_networks_data,
        interfaces=sorted(vm_nad_networks_data.keys()),
        client=unprivileged_client,
        cloud_init_data=cloud_init(ip_address="10.200.0.2"),
        body=fedora_vm_body(name=name),
        node_selector=worker_node1.hostname,
        running=True,
    ) as vm:
        yield vm


@pytest.fixture(scope="session")
def running_vma_upgrade_mac_spoof(vma_upgrade_mac_spoof):
    return running_vm(vm=vma_upgrade_mac_spoof)


@pytest.fixture(scope="session")
def running_vmb_upgrade_mac_spoof(vmb_upgrade_mac_spoof):
    return running_vm(vm=vmb_upgrade_mac_spoof)