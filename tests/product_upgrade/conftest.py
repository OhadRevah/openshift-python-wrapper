"""
VM to VM connectivity
"""

import pytest
from resources.template import Template
from tests.network.utils import linux_bridge_nad
from utilities.infra import create_ns
from utilities.network import LinuxBridgeNodeNetworkConfigurationPolicy, VXLANTunnel
from utilities.storage import DataVolumeTestResource
from utilities.virt import VirtualMachineForTestsFromTemplate, wait_for_vm_interfaces


@pytest.fixture(scope="module", autouse=True)
def upgrade_namespace(unprivileged_client):
    yield from create_ns(client=unprivileged_client, name="product-upgrade-test")


@pytest.fixture(scope="module", autouse=True)
def bridge_on_all_nodes(network_utility_pods, nodes_active_nics, multi_nics_nodes):
    ports = (
        [nodes_active_nics[network_utility_pods[0].node.name][1]]
        if multi_nics_nodes
        else []
    )
    with LinuxBridgeNodeNetworkConfigurationPolicy(
        name="upgrade-bridge",
        worker_pods=network_utility_pods,
        ports=ports,
        bridge_name="br1upgrade",
    ) as br:
        if not multi_nics_nodes:
            with VXLANTunnel(
                name="vxlan_upg_9",
                worker_pods=network_utility_pods,
                vxlan_id=9,
                master_bridge=br.bridge_name,
                nodes_nics=nodes_active_nics,
            ):
                yield br
        else:
            yield br


@pytest.fixture(scope="module", autouse=True)
def br1test_nad(upgrade_namespace, bridge_on_all_nodes):
    with linux_bridge_nad(
        namespace=upgrade_namespace,
        name=bridge_on_all_nodes.bridge_name,
        bridge=bridge_on_all_nodes.bridge_name,
    ) as nad:
        yield nad


def get_images_external_http_server():
    pass


@pytest.fixture(scope="module")
def data_volume(upgrade_namespace):
    template_labels = [
        f"{Template.Labels.OS}/rhel8.0",
        f"{Template.Labels.WORKLOAD}/server",
        f"{Template.Labels.FLAVOR}/tiny",
    ]
    with DataVolumeTestResource(
        name="dv-rhel8-server-tiny",
        namespace=upgrade_namespace.name,
        url=f"{get_images_external_http_server()}rhel-images/rhel-8/rhel-8.qcow2",
        os_release="8.0",
        template_labels=template_labels,
        access_modes=DataVolumeTestResource.AccessMode.RWX,
        volume_mode=DataVolumeTestResource.VolumeMode.BLOCK,
    ) as dv:
        dv.wait(timeout=900)
        yield dv


@pytest.fixture(scope="module")
def vm_for_upgrade(
    default_client,
    unprivileged_client,
    bridge_on_all_nodes,
    upgrade_namespace,
    data_volume,
):
    networks = {bridge_on_all_nodes.bridge_name: bridge_on_all_nodes.bridge_name}
    vm_name = "vm-for-product-upgrade"
    with VirtualMachineForTestsFromTemplate(
        name=vm_name,
        namespace=upgrade_namespace.name,
        client=default_client,
        labels=data_volume.template_labels,
        template_dv=data_volume.name,
        networks=networks,
        interfaces=sorted(networks.keys()),
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        wait_for_vm_interfaces(vmi=vm.vmi, timeout=1100)
        yield vm
