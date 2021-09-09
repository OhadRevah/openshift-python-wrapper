import logging
import re
from contextlib import contextmanager
from copy import deepcopy

import packaging.version
import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.machine_config_pool import MachineConfigPool
from ocp_resources.operator_hub import OperatorHub
from ocp_resources.resource import ResourceEditor
from ocp_resources.template import Template
from ocp_resources.utils import TimeoutSampler
from ocp_resources.virtual_machine import VirtualMachine
from pytest_testconfig import py_config

import tests.install_upgrade_operators.product_upgrade.utils as upgrade_utils
from utilities.constants import (
    KMP_ENABLED_LABEL,
    KMP_VM_ASSIGNMENT_LABEL,
    TIMEOUT_30MIN,
    TIMEOUT_40MIN,
)
from utilities.infra import create_ns
from utilities.network import (
    LINUX_BRIDGE,
    cloud_init_network_data,
    enable_hyperconverged_ovs_annotations,
    network_device,
    network_nad,
    wait_for_ovs_status,
)
from utilities.storage import (
    create_dv,
    get_images_server_url,
    sc_is_hpp_with_immediate_volume_binding,
)
from utilities.virt import (
    VirtualMachineForTests,
    VirtualMachineForTestsFromTemplate,
    fedora_vm_body,
    running_vm,
    wait_for_vm_interfaces,
)


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def kmp_enabled_namespace(kmp_vm_label, unprivileged_client, admin_client):
    # Enabling label "allocate" (or any other non-configured label) - Allocates.
    kmp_vm_label[KMP_VM_ASSIGNMENT_LABEL] = KMP_ENABLED_LABEL
    yield from create_ns(
        name="kmp-enabled-for-upgrade",
        kmp_vm_label=kmp_vm_label,
        unprivileged_client=unprivileged_client,
        admin_client=admin_client,
    )


@pytest.fixture(scope="module")
def upgrade_bridge_on_all_nodes(
    skip_if_no_multinic_nodes,
    utility_pods,
    hosts_common_available_ports,
    schedulable_nodes,
):
    with network_device(
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
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="upgrade-br-marker",
        interface_name="upg-br-mark",
        network_utility_pods=utility_pods,
        node_selector=worker_node1.name,
    ) as br:
        yield br


@pytest.fixture(scope="module")
def upgrade_bridge_marker_nad(bridge_on_one_node, kmp_enabled_namespace):
    with network_nad(
        nad_type=LINUX_BRIDGE,
        nad_name=bridge_on_one_node.bridge_name,
        interface_name=bridge_on_one_node.bridge_name,
        namespace=kmp_enabled_namespace,
        tuning=True,
    ) as nad:
        yield nad


def cloud_init(ip_address):
    network_data_data = {"ethernets": {"eth1": {"addresses": [f"{ip_address}/24"]}}}
    return cloud_init_network_data(data=network_data_data)


@pytest.fixture(scope="module")
def vm_upgrade_a(
    unprivileged_client,
    upgrade_bridge_marker_nad,
    kmp_enabled_namespace,
    upgrade_br1test_nad,
):
    name = "vm-upgrade-a"
    with VirtualMachineForTests(
        name=name,
        namespace=kmp_enabled_namespace.name,
        networks={upgrade_bridge_marker_nad.name: upgrade_bridge_marker_nad.name},
        interfaces=[upgrade_bridge_marker_nad.name],
        client=unprivileged_client,
        cloud_init_data=cloud_init(ip_address="10.200.100.1"),
        body=fedora_vm_body(name=name),
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def vm_upgrade_b(
    unprivileged_client,
    upgrade_bridge_marker_nad,
    kmp_enabled_namespace,
    upgrade_br1test_nad,
):
    name = "vm-upgrade-b"
    with VirtualMachineForTests(
        name=name,
        namespace=kmp_enabled_namespace.name,
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


@pytest.fixture(scope="module")
def upgrade_br1test_nad(namespace, upgrade_bridge_on_all_nodes):
    with network_nad(
        nad_type=LINUX_BRIDGE,
        nad_name=upgrade_bridge_on_all_nodes.bridge_name,
        interface_name=upgrade_bridge_on_all_nodes.bridge_name,
        namespace=namespace,
        tuning=True,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def dvs_for_upgrade(admin_client, worker_node1, rhel_latest_os_params):
    dvs_list = []
    for sc in py_config["system_storage_class_matrix"]:
        storage_class = [*sc][0]
        dv = DataVolume(
            client=admin_client,
            name=f"dv-for-product-upgrade-{storage_class}",
            namespace=py_config["golden_images_namespace"],
            source="http",
            storage_class=storage_class,
            volume_mode=sc[storage_class]["volume_mode"],
            access_modes=sc[storage_class]["access_mode"],
            url=rhel_latest_os_params["rhel_image_path"],
            size=rhel_latest_os_params["rhel_dv_size"],
            bind_immediate_annotation=True,
            hostpath_node=worker_node1.name
            if sc_is_hpp_with_immediate_volume_binding(sc=storage_class)
            else None,
            privileged_client=admin_client,
        )
        dv.create()
        dvs_list.append(dv)
    upgrade_utils.wait_for_dvs_import_completed(dvs_list=dvs_list)

    yield dvs_list

    for dv in dvs_list:
        dv.clean_up()


@pytest.fixture(scope="module")
def vms_for_upgrade(
    unprivileged_client,
    namespace,
    vm_bridge_networks,
    dvs_for_upgrade,
    upgrade_br1test_nad,
    nodes_common_cpu_model,
    rhel_latest_os_params,
):
    vms_list = []
    for dv in dvs_for_upgrade:
        vm = VirtualMachineForTestsFromTemplate(
            name=dv.name.replace("dv", "vm")[0:26],
            namespace=namespace.name,
            client=unprivileged_client,
            labels=Template.generate_template_labels(
                **rhel_latest_os_params["rhel_template_labels"]
            ),
            data_volume=dv,
            networks=vm_bridge_networks,
            cpu_model=nodes_common_cpu_model,
            interfaces=sorted(vm_bridge_networks.keys()),
        )
        vm.deploy()
        vm.start(timeout=TIMEOUT_40MIN, wait=False)
        vms_list.append(vm)

    for vm in vms_list:
        running_vm(vm=vm)

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
def cnv_upgrade_path(
    request, admin_client, cnv_upgrade, pytestconfig, cnv_current_version
):
    if cnv_upgrade:
        cnv_target_version = pytestconfig.option.cnv_version
        current_version = packaging.version.parse(version=cnv_current_version)
        target_version = packaging.version.parse(version=cnv_target_version)
        # skip version check if --cnv-upgrade-skip-version-check is used.
        # This allows upgrading to a newer build on the same Z stream (for dev purposes)
        if (
            not request.session.config.getoption("--cnv-upgrade-skip-version-check")
            and target_version <= current_version
        ):
            # Upgrade only if a newer CNV version is requested
            raise ValueError(
                f"Cannot upgrade to older/identical versions,"
                f"current: {cnv_current_version} target: {cnv_target_version}"
            )

        if current_version.major < target_version.major:
            upgrade_stream = "x-stream"
        elif current_version.minor < target_version.minor:
            upgrade_stream = "y-stream"
        elif current_version.micro < target_version.micro:
            upgrade_stream = "z-stream"
        elif current_version.release == target_version.release:
            upgrade_stream = "dev-stream"
        else:
            raise ValueError(
                f"unknown upgrade stream, current: {cnv_current_version} target: {cnv_target_version}"
            )

        cnv_upgrade_dict = {
            "current_version": cnv_current_version,
            "target_version": cnv_target_version,
            "upgrade_stream": upgrade_stream,
            "target_channel": f"{target_version.major}.{target_version.minor}",
        }

        return cnv_upgrade_dict


@pytest.fixture(scope="module")
def vms_for_upgrade_dict_before(vms_for_upgrade):
    vms_dict = {}
    for vm in vms_for_upgrade:
        vms_dict[vm.name] = deepcopy(vm.instance.to_dict())
    yield vms_dict


@pytest.fixture(scope="module")
def nodes_taints_before_upgrade(nodes):
    return upgrade_utils.get_nodes_taints(nodes=nodes)


@pytest.fixture(scope="module")
def nodes_labels_before_upgrade(nodes):
    return upgrade_utils.get_nodes_labels(nodes=nodes)


@pytest.fixture()
def update_image_content_source(
    is_deployment_from_production_source,
    is_deployment_from_stage_source,
    pytestconfig,
    cnv_image_name,
    cnv_registry_source,
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

    if is_deployment_from_stage_source:
        upgrade_utils.update_icsp_stage_mirror(icsp_file_path=icsp_file_path)

    LOGGER.info("pausing MCP updates while modifying ICSP")
    with ResourceEditor(
        patches={
            mcp: {"spec": {"paused": True}}
            for mcp in MachineConfigPool.get(dyn_client=admin_client)
        }
    ):
        # delete the existing ICSP and then create the new one
        # apply is not good enough due to the amount of annotations we have
        # the amount of annotations we have is greater than the maximum size of a payload that is supported with apply
        LOGGER.info("Deleting existing ICSP.")
        upgrade_utils.delete_icsp(admin_client=admin_client)

        LOGGER.info("Creating new ICSP.")
        upgrade_utils.create_icsp_from_file(icsp_file_path=icsp_file_path)

    LOGGER.info("Wait for MCP to update now that we modified the ICSP")
    upgrade_utils.wait_for_mcp_update(dyn_client=admin_client)


@pytest.fixture(scope="module")
def skip_if_less_than_two_storage_classes(cluster_storage_classes):
    if len(cluster_storage_classes) < 2:
        pytest.skip(msg="Need two Storage Classes at least.")


@pytest.fixture(scope="module")
def storage_class_for_updating_cdiconfig_scratch(
    skip_if_less_than_two_storage_classes, cdi_config, cluster_storage_classes
):
    """
    Choose one StorageClass which is not the current one for scratch space.
    """
    current_sc_for_scratch = cdi_config.scratch_space_storage_class_from_status
    LOGGER.info(
        f"The current StorageClass for scratch space on CDIConfig is: {current_sc_for_scratch}"
    )
    for sc in cluster_storage_classes:
        if sc.instance.metadata.get("name") != current_sc_for_scratch:
            LOGGER.info(f"Candidate StorageClass: {sc.instance.metadata.name}")
            return sc


@pytest.fixture(scope="module")
def override_cdiconfig_scratch_spec(
    cdi,
    cdi_config,
    storage_class_for_updating_cdiconfig_scratch,
):
    """
    Change spec.scratchSpaceStorageClass to the selected StorageClass on CDIConfig.
    """
    if storage_class_for_updating_cdiconfig_scratch:
        new_sc = storage_class_for_updating_cdiconfig_scratch.name

        def _wait_for_sc_update():
            samples = TimeoutSampler(
                wait_timeout=30,
                sleep=1,
                func=lambda: cdi_config.scratch_space_storage_class_from_status
                == new_sc,
            )
            for sample in samples:
                if sample:
                    return

        with ResourceEditor(
            patches={cdi: {"spec": {"config": {"scratchSpaceStorageClass": new_sc}}}}
        ) as edited_cdi_config:
            _wait_for_sc_update()

            yield edited_cdi_config


@pytest.fixture(scope="module")
def skip_if_not_override_cdiconfig_scratch_space(override_cdiconfig_scratch_spec):
    if not override_cdiconfig_scratch_spec:
        pytest.skip(msg="Skip test because the scratch space was not changed.")


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


@pytest.fixture(scope="module")
def unupdated_vmi_pods_names(
    admin_client,
    hco_namespace,
    hco_target_version,
    vms_for_upgrade,
):

    target_related_images_name_and_versions = (
        upgrade_utils.get_related_images_name_and_version(
            dyn_client=admin_client,
            hco_namespace=hco_namespace.name,
            version=hco_target_version,
        )
    )

    return [
        {pod.name: pod.instance.spec.containers[0].image}
        for pod in [vm.vmi.virt_launcher_pod for vm in vms_for_upgrade]
        if pod.instance.spec.containers[0].image
        not in upgrade_utils.cnv_target_images(
            target_related_images_name_and_versions=target_related_images_name_and_versions
        )
    ]


@pytest.fixture(scope="module")
def run_strategy_golden_image_rwx_dv(dvs_for_upgrade):
    return [
        dv
        for dv in dvs_for_upgrade
        if DataVolume.AccessMode.RWX in dv.pvc.instance.spec.accessModes
    ][0]


@pytest.fixture(scope="module")
def vm_bridge_networks(upgrade_bridge_on_all_nodes):
    return {
        upgrade_bridge_on_all_nodes.bridge_name: upgrade_bridge_on_all_nodes.bridge_name
    }


@contextmanager
def vm_from_template(
    client,
    namespace,
    vm_name,
    data_volume,
    cpu_model,
    networks,
    template_labels,
    run_strategy=None,
):
    with VirtualMachineForTestsFromTemplate(
        name=vm_name,
        namespace=namespace,
        client=client,
        labels=Template.generate_template_labels(**template_labels),
        data_volume=data_volume,
        cpu_model=cpu_model,
        run_strategy=run_strategy,
        networks=networks,
        interfaces=sorted(networks.keys()),
    ) as vm:
        yield vm


@pytest.fixture(scope="module")
def manual_run_strategy_vm(
    unprivileged_client,
    namespace,
    vm_bridge_networks,
    run_strategy_golden_image_rwx_dv,
    nodes_common_cpu_model,
    rhel_latest_os_params,
):
    with vm_from_template(
        vm_name="manual-run-strategy-vm",
        namespace=namespace.name,
        client=unprivileged_client,
        template_labels=rhel_latest_os_params["rhel_template_labels"],
        data_volume=run_strategy_golden_image_rwx_dv,
        run_strategy=VirtualMachine.RunStrategy.MANUAL,
        cpu_model=nodes_common_cpu_model,
        networks=vm_bridge_networks,
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture(scope="module")
def always_run_strategy_vm(
    unprivileged_client,
    namespace,
    vm_bridge_networks,
    upgrade_br1test_nad,
    run_strategy_golden_image_rwx_dv,
    nodes_common_cpu_model,
    rhel_latest_os_params,
):
    with vm_from_template(
        vm_name="always-run-strategy-vm",
        namespace=namespace.name,
        client=unprivileged_client,
        template_labels=rhel_latest_os_params["rhel_template_labels"],
        data_volume=run_strategy_golden_image_rwx_dv,
        run_strategy=VirtualMachine.RunStrategy.ALWAYS,
        cpu_model=nodes_common_cpu_model,
        networks=vm_bridge_networks,
    ) as vm:
        # No need to start the VM as the VM will be automatically started (RunStrategy Always)
        yield vm


@pytest.fixture()
def running_manual_run_strategy_vm(manual_run_strategy_vm):
    running_vm(vm=manual_run_strategy_vm, check_ssh_connectivity=False)


@pytest.fixture()
def running_always_run_strategy_vm(always_run_strategy_vm):
    running_vm(vm=always_run_strategy_vm, check_ssh_connectivity=False)


@pytest.fixture(scope="module")
def rhel_latest_os_params():
    """This fixture is needed as during collection pytest_testconfig is empty.
    os_params or any globals using py_config in conftest cannot be used.
    """
    latest_rhel_dict = py_config["latest_rhel_os_dict"]
    return {
        "rhel_image_path": f"{get_images_server_url(schema='http')}{latest_rhel_dict['image_path']}",
        "rhel_dv_size": latest_rhel_dict["dv_size"],
        "rhel_template_labels": latest_rhel_dict["template_labels"],
    }


@pytest.fixture(scope="module")
def windows_vm(
    admin_client,
    unprivileged_client,
    namespace,
    vm_bridge_networks,
    upgrade_br1test_nad,
    nodes_common_cpu_model,
):
    latest_windows_dict = py_config["latest_windows_os_dict"]
    with create_dv(
        client=admin_client,
        dv_name=latest_windows_dict["os_version"],
        namespace=py_config["golden_images_namespace"],
        url=f"{get_images_server_url(schema='http')}{latest_windows_dict['image_path']}",
        storage_class=py_config["default_storage_class"],
        access_modes=py_config["default_access_mode"],
        volume_mode=py_config["default_volume_mode"],
        size=latest_windows_dict["dv_size"],
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.SUCCEEDED, timeout=TIMEOUT_30MIN)
        with vm_from_template(
            vm_name="windows-vm",
            namespace=namespace.name,
            client=unprivileged_client,
            template_labels=latest_windows_dict["template_labels"],
            data_volume=dv,
            cpu_model=nodes_common_cpu_model,
            networks=vm_bridge_networks,
        ) as vm:
            running_vm(vm=vm, check_ssh_connectivity=False)
            yield vm
