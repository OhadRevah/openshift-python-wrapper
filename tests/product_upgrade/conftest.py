from copy import deepcopy

import pytest
import tests.network.utils as network_utils
import tests.product_upgrade.utils as upgrade_utils
import utilities.network
from pytest_testconfig import py_config
from resources.datavolume import DataVolume
from resources.operator_hub import OperatorHub
from resources.operator_source import OperatorSource
from resources.resource import ResourceEditor
from resources.secret import Secret
from resources.template import Template
from tests.network.utils import nmcli_add_con_cmds
from utilities.storage import get_images_external_http_server
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
    skip_if_no_multinic_nodes, utility_pods, nodes_active_nics, schedulable_nodes,
):
    with network_utils.network_device(
        interface_type=utilities.network.LINUX_BRIDGE,
        nncp_name="upgrade-bridge",
        interface_name="br1upgrade",
        network_utility_pods=utility_pods,
        nodes=schedulable_nodes,
        ports=[
            utilities.network.get_hosts_common_ports(
                nodes_active_nics=nodes_active_nics
            )[1]
        ],
    ) as br:
        yield br


@pytest.fixture(scope="module")
def bridge_on_one_node(utility_pods, worker_node1):
    with network_utils.network_device(
        interface_type=utilities.network.LINUX_BRIDGE,
        nncp_name="upgrade-br-marker",
        interface_name="upg-br-mark",
        network_utility_pods=utility_pods,
        node_selector=worker_node1.name,
    ) as br:
        yield br


@pytest.fixture(scope="module")
def upgrade_bridge_marker_nad(bridge_on_one_node, namespace):
    with utilities.network.network_nad(
        nad_type=utilities.network.LINUX_BRIDGE,
        nad_name=bridge_on_one_node.bridge_name,
        interface_name=bridge_on_one_node.bridge_name,
        namespace=namespace,
    ) as nad:
        yield nad


def cloud_init(ip_address):
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    bootcmds = nmcli_add_con_cmds(iface="eth1", ip=ip_address)
    cloud_init_data["bootcmd"] = bootcmds
    return cloud_init_data


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
    with utilities.network.network_nad(
        nad_type=utilities.network.LINUX_BRIDGE,
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
            if storage_class == "hostpath-provisioner"
            else None,
        )
        dv.create()
        dvs_list.append(dv)
    upgrade_utils.wait_for_dvs_import_completed(dvs_list=dvs_list)

    yield dvs_list

    for dv in dvs_list:
        dv.clean_up()


@pytest.fixture(scope="module")
def vms_for_upgrade(unprivileged_client, upgrade_bridge_on_all_nodes, dvs_for_upgrade):
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
            template_dv=dv,
            networks=networks,
            interfaces=sorted(networks.keys()),
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
def operatorhub_no_default_sources(default_client, cnv_upgrade):
    if cnv_upgrade:
        for source in OperatorHub.get(dyn_client=default_client):
            ResourceEditor(
                patches={source: {"spec": {"disableAllDefaultSources": True}}}
            ).update()


@pytest.fixture(scope="session")
def cnv_upgrade_path(default_client, cnv_upgrade, pytestconfig, cnv_current_version):
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
