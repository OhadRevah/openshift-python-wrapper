"""
VM to VM connectivity
"""
import pytest
import tests.network.utils as network_utils
from pytest_testconfig import py_config
from resources.configmap import ConfigMap
from resources.datavolume import DataVolume
from resources.template import Template
from tests.network.kubemacpool.conftest import KUBEMACPOOL_CONFIG_MAP_NAME
from tests.network.utils import nmcli_add_con_cmds
from utilities.infra import Images, create_ns, get_images_external_http_server
from utilities.storage import create_dv
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    VirtualMachineForTestsFromTemplate,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


@pytest.fixture(scope="module", autouse=True)
def upgrade_namespace(unprivileged_client):
    yield from create_ns(client=unprivileged_client, name="product-upgrade-test")


@pytest.fixture(scope="module", autouse=True)
def bridge_on_all_nodes(
    network_utility_pods, nodes_active_nics, multi_nics_nodes, schedulable_nodes
):
    ports = (
        [nodes_active_nics[network_utility_pods[0].node.name][1]]
        if multi_nics_nodes
        else []
    )

    with network_utils.bridge_device(
        bridge_type=network_utils.LINUX_BRIDGE,
        nncp_name="upgrade-bridge",
        bridge_name="br1upgrade",
        network_utility_pods=network_utility_pods,
        nodes=schedulable_nodes,
        ports=ports,
        nodes_active_nics=nodes_active_nics,
    ) as br:
        yield br


@pytest.fixture(scope="module")
def bridge_on_one_node(network_utility_pods, schedulable_nodes):
    with network_utils.bridge_device(
        bridge_type=network_utils.LINUX_BRIDGE,
        nncp_name="upgrade-br-marker",
        bridge_name="upg-br-mark",
        network_utility_pods=[network_utility_pods[0]],
        nodes=schedulable_nodes,
        node_selector=network_utility_pods[0].node.name,
        vxlan=False,
    ) as br:
        yield br


@pytest.fixture(scope="module")
def upgrade_bridge_marker_nad(bridge_on_one_node, upgrade_namespace):
    with network_utils.bridge_nad(
        nad_type=network_utils.LINUX_BRIDGE,
        nad_name=bridge_on_one_node.bridge_name,
        bridge_name=bridge_on_one_node.bridge_name,
        namespace=upgrade_namespace,
    ) as nad:
        yield nad


def cloud_init(ip_address):
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    bootcmds = nmcli_add_con_cmds(iface="eth1", ip=ip_address)
    cloud_init_data["bootcmd"] = bootcmds
    return cloud_init_data


@pytest.fixture(scope="module")
def vm_upgrade_a(upgrade_bridge_marker_nad, upgrade_namespace, unprivileged_client):
    name = "vm-upgrade-a"
    with VirtualMachineForTests(
        name=name,
        namespace=upgrade_namespace.name,
        networks={upgrade_bridge_marker_nad.name: upgrade_bridge_marker_nad.name},
        interfaces=[upgrade_bridge_marker_nad.name],
        client=unprivileged_client,
        cloud_init_data=cloud_init("192.168.100.1"),
        body=fedora_vm_body(name),
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def vm_upgrade_b(upgrade_bridge_marker_nad, upgrade_namespace, unprivileged_client):
    name = "vm-upgrade-b"
    with VirtualMachineForTests(
        name=name,
        namespace=upgrade_namespace.name,
        networks={upgrade_bridge_marker_nad.name: upgrade_bridge_marker_nad.name},
        interfaces=[upgrade_bridge_marker_nad.name],
        client=unprivileged_client,
        cloud_init_data=cloud_init("192.168.100.2"),
        body=fedora_vm_body(name),
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def running_vm_a(vm_upgrade_a):
    vmi = vm_upgrade_a.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    return vm_upgrade_a


@pytest.fixture(scope="module")
def running_vm_b(vm_upgrade_b):
    vmi = vm_upgrade_b.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    return vm_upgrade_b


@pytest.fixture(scope="module")
def kubemacpool_configmap(upgrade_namespace):
    kubemacpool_config_map = ConfigMap(
        namespace=py_config["hco_namespace"], name=KUBEMACPOOL_CONFIG_MAP_NAME
    )
    return kubemacpool_config_map


@pytest.fixture(scope="module", autouse=True)
def br1test_nad(upgrade_namespace, bridge_on_all_nodes):
    with network_utils.bridge_nad(
        nad_type=network_utils.LINUX_BRIDGE,
        nad_name=bridge_on_all_nodes.bridge_name,
        bridge_name=bridge_on_all_nodes.bridge_name,
        namespace=upgrade_namespace,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def data_volume(upgrade_namespace):
    with create_dv(
        source="http",
        dv_name="dv-rhel8-server-tiny",
        size="25Gi",
        namespace=upgrade_namespace.name,
        url=f"{get_images_external_http_server()}{Images.Rhel.DIR}/{Images.Rhel.RHEL8_0_IMG}",
        volume_mode=DataVolume.VolumeMode.BLOCK,
        access_modes=DataVolume.AccessMode.RWX,
        content_type=DataVolume.ContentType.KUBEVIRT,
        storage_class=py_config["default_storage_class"],
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
    template_labels_dict = {
        "os": "rhel8.0",
        "workload": "server",
        "flavor": "tiny",
    }
    networks = {bridge_on_all_nodes.bridge_name: bridge_on_all_nodes.bridge_name}
    vm_name = "vm-for-product-upgrade"
    with VirtualMachineForTestsFromTemplate(
        name=vm_name,
        namespace=upgrade_namespace.name,
        client=default_client,
        labels=Template.generate_template_labels(**template_labels_dict),
        template_dv=data_volume,
        networks=networks,
        interfaces=sorted(networks.keys()),
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        wait_for_vm_interfaces(vmi=vm.vmi, timeout=1100)
        yield vm
