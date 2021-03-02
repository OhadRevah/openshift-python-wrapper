from copy import deepcopy

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.operator_hub import OperatorHub
from ocp_resources.operator_source import OperatorSource
from ocp_resources.resource import ResourceEditor
from ocp_resources.secret import Secret
from ocp_resources.template import Template
from pytest_testconfig import py_config

import tests.install_upgrade_operators.product_upgrade.utils as upgrade_utils
import utilities.network
from utilities import console
from utilities.network import (
    LINUX_BRIDGE,
    cloud_init_network_data,
    enable_hyperconverged_ovs_annotations,
    network_nad,
    wait_for_ovs_status,
)
from utilities.storage import (
    get_images_external_http_server,
    sc_is_hpp_with_immediate_volume_binding,
)
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    VirtualMachineForTestsFromTemplate,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


MARKETPLACE_NAMESPACE = "openshift-marketplace"


@pytest.fixture(scope="module", autouse=True)
def upgrade_bridge_on_all_nodes(
    skip_if_no_multinic_nodes,
    utility_pods,
    hosts_common_available_ports,
    schedulable_nodes,
):
    with utilities.network.network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="upgrade-bridge",
        interface_name="br1upgrade",
        network_utility_pods=utility_pods,
        nodes=schedulable_nodes,
        ports=[hosts_common_available_ports[0]],
    ) as br:
        yield br


@pytest.fixture(scope="module")
def bridge_on_one_node(utility_pods, worker_node1):
    with utilities.network.network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="upgrade-br-marker",
        interface_name="upg-br-mark",
        network_utility_pods=utility_pods,
        node_selector=worker_node1.name,
    ) as br:
        yield br


@pytest.fixture(scope="module")
def upgrade_bridge_marker_nad(bridge_on_one_node, namespace):
    with network_nad(
        nad_type=LINUX_BRIDGE,
        nad_name=bridge_on_one_node.bridge_name,
        interface_name=bridge_on_one_node.bridge_name,
        namespace=namespace,
    ) as nad:
        yield nad


def cloud_init(ip_address):
    network_data_data = {"ethernets": {"eth1": {"addresses": [f"{ip_address}/24"]}}}
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data.update(cloud_init_network_data(data=network_data_data))


@pytest.fixture(scope="module")
def vm_upgrade_a(upgrade_bridge_marker_nad, namespace, unprivileged_client):
    name = "vm-upgrade-a"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        networks={upgrade_bridge_marker_nad.name: upgrade_bridge_marker_nad.name},
        interfaces=[upgrade_bridge_marker_nad.name],
        client=unprivileged_client,
        cloud_init_data=cloud_init(ip_address="10.200.100.1"),
        body=fedora_vm_body(name=name),
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def vm_upgrade_b(upgrade_bridge_marker_nad, namespace, unprivileged_client):
    name = "vm-upgrade-b"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        networks={upgrade_bridge_marker_nad.name: upgrade_bridge_marker_nad.name},
        interfaces=[upgrade_bridge_marker_nad.name],
        client=unprivileged_client,
        cloud_init_data=cloud_init(ip_address="10.200.100.2"),
        body=fedora_vm_body(name=name),
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def running_vm_upgrade_a(vm_upgrade_a):
    vmi = vm_upgrade_a.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    return vm_upgrade_a


@pytest.fixture(scope="module")
def running_vm_upgrade_b(vm_upgrade_b):
    vmi = vm_upgrade_b.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    return vm_upgrade_b


@pytest.fixture(scope="module", autouse=True)
def upgrade_br1test_nad(namespace, upgrade_bridge_on_all_nodes):
    with network_nad(
        nad_type=LINUX_BRIDGE,
        nad_name=upgrade_bridge_on_all_nodes.bridge_name,
        interface_name=upgrade_bridge_on_all_nodes.bridge_name,
        namespace=namespace,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def dvs_for_upgrade(namespace, worker_node1):
    dvs_list = []
    for sc in py_config["system_storage_class_matrix"]:
        storage_class = [*sc][0]
        dv = DataVolume(
            name=f"dv-for-product-upgrade-{storage_class}",
            namespace=namespace.name,
            source="http",
            storage_class=storage_class,
            volume_mode=sc[storage_class]["volume_mode"],
            access_modes=sc[storage_class]["access_mode"],
            url=f"{get_images_external_http_server()}{py_config['latest_rhel_version']['image_path']}",
            size="25Gi",
            hostpath_node=worker_node1.name
            if sc_is_hpp_with_immediate_volume_binding(sc=storage_class)
            else None,
        )
        dv.create()
        dvs_list.append(dv)
    upgrade_utils.wait_for_dvs_import_completed(dvs_list=dvs_list)

    yield dvs_list

    for dv in dvs_list:
        dv.clean_up()


@pytest.fixture(scope="module")
def vms_for_upgrade(
    unprivileged_client, upgrade_bridge_on_all_nodes, dvs_for_upgrade, rhel7_workers
):
    networks = {
        upgrade_bridge_on_all_nodes.bridge_name: upgrade_bridge_on_all_nodes.bridge_name
    }
    template_labels = py_config["latest_rhel_version"]["template_labels"]
    vms_list = []
    for dv in dvs_for_upgrade:
        vm = VirtualMachineForTestsFromTemplate(
            name=dv.name.replace("dv", "vm"),
            namespace=dv.namespace,
            client=unprivileged_client,
            labels=Template.generate_template_labels(**template_labels),
            data_volume=dv,
            networks=networks,
            interfaces=sorted(networks.keys()),
            username=console.RHEL.USERNAME,
            password=console.RHEL.PASSWORD,
            rhel7_workers=rhel7_workers,
        )
        vm.create()
        vms_list.append(vm)
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        vm.ssh_enable()
    upgrade_utils.wait_for_vms_interfaces(vms_list=vms_list)

    yield vms_list

    for vm in vms_list:
        vm.clean_up()


@pytest.fixture(scope="session")
def cnv_upgrade(pytestconfig):
    """ Returns True if requested upgrade if for CNV else False """
    return pytestconfig.option.upgrade == "cnv"


@pytest.fixture()
def registry_secret(cnv_upgrade):
    if cnv_upgrade:
        token = (
            "basic cmgtb3Nicy1vcGVyYXRvcnMrY252cWU6MDBVSjc0ME1LRUpEWlVTVDBaMlRMW"
            "lZRRlE2SFJVUDAxTldWNFpWQTBHVzFORUxWT0FKOVVUWVBUMkgzTlowVg=="
        )
        with Secret(
            name=f"quay-registry-{upgrade_utils.APP_REGISTRY}",
            namespace=MARKETPLACE_NAMESPACE,
            string_data={"token": token},
        ) as secret:
            yield secret
    else:
        yield


@pytest.fixture()
def operator_source(registry_secret):
    if registry_secret:
        with OperatorSource(
            name=upgrade_utils.APP_REGISTRY,
            namespace=MARKETPLACE_NAMESPACE,
            registry_namespace=upgrade_utils.APP_REGISTRY,
            display_name=upgrade_utils.APP_REGISTRY,
            publisher="Red Hat",
            secret=registry_secret.name,
        ) as os:
            yield os
    else:
        yield


@pytest.fixture()
def operatorhub_no_default_sources(admin_client, cnv_upgrade):
    if cnv_upgrade:
        for source in OperatorHub.get(dyn_client=admin_client):
            ResourceEditor(
                patches={source: {"spec": {"disableAllDefaultSources": True}}}
            ).update()


@pytest.fixture(scope="session")
def cnv_upgrade_path(admin_client, cnv_upgrade, pytestconfig, cnv_current_version):
    if cnv_upgrade:
        cnv_target_version = pytestconfig.option.cnv_version
        # Upgrade only if a newer CNV version is requested
        if int(cnv_target_version.replace(".", "")) <= int(
            cnv_current_version.replace(".", "")
        ):
            raise ValueError(
                f"Cannot upgrade to older/identical versions,"
                f"current: {cnv_current_version} target: {cnv_target_version}"
            )

        cnv_upgrade_dict = {
            "current_version": cnv_current_version,
            "target_version": cnv_target_version,
        }
        (
            cnv_upgrade_dict["upgrade_path"],
            cnv_upgrade_dict["target_channel"],
        ) = upgrade_utils.upgrade_path(cnv_upgrade_dict=cnv_upgrade_dict)

        return cnv_upgrade_dict


@pytest.fixture(scope="module")
def vms_for_upgrade_dict_before(vms_for_upgrade):
    vms_dict = {}
    for vm in vms_for_upgrade:
        vms_dict[vm.name] = deepcopy(vm.instance.to_dict())
    yield vms_dict


@pytest.fixture(scope="module")
def nodes_status_before_upgrade(nodes):
    return upgrade_utils.get_nodes_status(nodes=nodes)


@pytest.fixture(scope="class")
def hyperconverged_ovs_annotations_enabled_scope_class(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_class,
    network_addons_config,
):
    yield from enable_hyperconverged_ovs_annotations(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        hyperconverged_resource=hyperconverged_resource_scope_class,
        network_addons_config=network_addons_config,
    )

    wait_for_ovs_status(network_addons_config=network_addons_config, status=False)
