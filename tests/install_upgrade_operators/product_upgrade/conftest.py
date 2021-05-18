import logging
import re
from copy import deepcopy

import packaging.version
import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.operator_hub import OperatorHub
from ocp_resources.resource import ResourceEditor
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
    get_images_server_url,
    sc_is_hpp_with_immediate_volume_binding,
)
from utilities.virt import (
    VirtualMachineForTests,
    VirtualMachineForTestsFromTemplate,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


LOGGER = logging.getLogger(__name__)


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
    return cloud_init_network_data(data=network_data_data)


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
            url=f"{get_images_server_url(schema='http')}{py_config['latest_rhel_os_dict']['image_path']}",
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
    template_labels = py_config["latest_rhel_os_dict"]["template_labels"]
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
def cnv_image_name(pytestconfig):
    cnv_image_url = pytestconfig.option.cnv_image
    if not cnv_image_url:
        return

    # Image name format example staging: registry-proxy-stage.engineering.redhat.com/rh-osbs-stage/iib:v4.5
    # Image name format example osbs: registry-proxy.engineering.redhat.com/rh-osbs/iib:45131
    try:
        return re.search(r"[/.*](\w+):", cnv_image_url).group(1)
    except IndexError:
        LOGGER.error(
            "Can not find CNV image name "
            "(example: registry-proxy.engineering.redhat.com/rh-osbs/iib:45131 should find 'iib')"
        )
        raise


@pytest.fixture()
def operatorhub_without_default_sources(
    cnv_upgrade, admin_client, is_deployment_from_production_source
):
    if cnv_upgrade and not is_deployment_from_production_source:
        for source in OperatorHub.get(dyn_client=admin_client):
            with ResourceEditor(
                patches={source: {"spec": {"disableAllDefaultSources": True}}}
            ) as edited_source:
                yield edited_source
    else:
        yield


@pytest.fixture(scope="session")
def cnv_upgrade_path(admin_client, cnv_upgrade, pytestconfig, cnv_current_version):
    if cnv_upgrade:
        cnv_target_version = pytestconfig.option.cnv_version
        # Upgrade only if a newer CNV version is requested
        if packaging.version.parse(cnv_target_version) <= packaging.version.parse(
            cnv_current_version
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


@pytest.fixture()
def update_image_content_source(
    is_deployment_from_production_source,
    pytestconfig,
    cnv_image_name,
    cnv_registry_source,
    cnv_source,
    admin_client,
    cnv_upgrade,
    tmpdir,
):
    if not cnv_upgrade or is_deployment_from_production_source:
        # not needed when upgrading OCP
        # Generate ICSP only in case of deploying from OSBS or Stage source; Production source does not require ICSP.
        return

    icsp_file_path = upgrade_utils.generate_icsp_file(
        tmpdir=tmpdir,
        cnv_index_image=pytestconfig.option.cnv_image,
        cnv_image_name=cnv_image_name,
        source_map=cnv_registry_source["source_map"],
    )

    if cnv_source == "stage":
        upgrade_utils.update_icsp_stage_mirror(icsp_file_path=icsp_file_path)

    LOGGER.info("Deleting existing ICSP.")
    # delete the existing ICSP and then create the new one
    # apply is not good enough due to the amount of annotations we have
    # the amount of annotations we have is greater than the maximum size of a payload that is supported with apply
    upgrade_utils.delete_icsp(admin_client=admin_client)
    # when changes are made to the ICSP (like deleting it), it takes time to take effect on all nodes,
    # The indicator for this is the MCP conditions (updating, then updated)
    # Must wait to check that the MCP accepted the change
    # If the ICSP creation is executed right after deletion without waiting the MCP update process might not progress
    upgrade_utils.wait_for_mcp_update(dyn_client=admin_client)

    LOGGER.info("Creating new ICSP.")
    upgrade_utils.create_icsp_from_file(icsp_file_path=icsp_file_path)
    upgrade_utils.wait_for_mcp_update(dyn_client=admin_client)


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
