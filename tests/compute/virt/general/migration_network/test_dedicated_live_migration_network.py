import logging

import pytest
from ocp_resources.template import Template
from pytest_testconfig import config as py_config

from tests.compute.utils import update_hco_annotations
from tests.compute.virt.general.migration_network.utils import (
    MACVLANNetworkAttachmentDefinition,
    assert_node_drain_and_vm_migration,
    assert_vm_migrated_through_dedicated_network_with_logs,
    assert_vm_migrated_through_dedicated_network_with_tcpdump,
    get_virt_handler_pods,
    migrate_and_verify_multi_vms,
    run_tcpdump_on_source_node,
    taint_node_no_schedule,
    wait_for_virt_handler_pods_network_updated,
)
from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS
from utilities.virt import (
    VirtualMachineForTestsFromTemplate,
    migrate_vm_and_verify,
    running_vm,
    wait_for_updated_kv_value,
)


LOGGER = logging.getLogger(__name__)
TESTS_CLASS_NAME = "TestDedicatedLiveMigrationNetwork"


@pytest.fixture(scope="module")
def migration_interface(hosts_common_available_ports):
    return hosts_common_available_ports[-1]


@pytest.fixture(scope="module")
def dedicated_network_nad(migration_interface, hco_namespace):
    with MACVLANNetworkAttachmentDefinition(
        name="migration-nad",
        namespace=hco_namespace.name,
        master=migration_interface,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def dedicated_migration_network_hco_config(
    admin_client,
    hco_namespace,
    virt_handler_daemonset_scope_module,
    hyperconverged_resource_scope_module,
    dedicated_network_nad,
):
    # TODO: Change from json annotation to hco modification when HCO PR is ready
    # https://github.com/kubevirt/hyperconverged-cluster-operator/pull/1685
    path = "migrations/network"
    with update_hco_annotations(
        resource=hyperconverged_resource_scope_module,
        path=path,
        value=dedicated_network_nad.name,
    ):
        wait_for_updated_kv_value(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            path=path.split("/"),
            value=dedicated_network_nad.name,
        )
        wait_for_virt_handler_pods_network_updated(
            client=admin_client,
            namespace=hco_namespace,
            network_name=dedicated_network_nad.name,
            virt_handler_daemonset=virt_handler_daemonset_scope_module,
        )
        yield

    wait_for_virt_handler_pods_network_updated(
        client=admin_client,
        namespace=hco_namespace,
        network_name=dedicated_network_nad.name,
        virt_handler_daemonset=virt_handler_daemonset_scope_module,
        migration_network=False,
    )


@pytest.fixture(scope="class")
def migration_vm_1(
    namespace,
    unprivileged_client,
    golden_image_data_source_scope_class,
):
    with VirtualMachineForTestsFromTemplate(
        name="migration-vm-1",
        labels=Template.generate_template_labels(**RHEL_LATEST_LABELS),
        namespace=namespace.name,
        client=unprivileged_client,
        data_source=golden_image_data_source_scope_class,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def tainted_all_nodes_but_one(schedulable_nodes, migration_vm_1):
    # Taint all nodes NoSchedule except one where migration_vm_1 is deployed
    # to ensure 2nd vm is deployed on same node
    node_editors = [
        taint_node_no_schedule(node)
        for node in schedulable_nodes
        if node.name != migration_vm_1.vmi.node.name
    ]
    for editor in node_editors:
        editor.update(backup_resources=True)

    yield node_editors

    for editor in node_editors:
        editor.restore()


@pytest.fixture()
def migration_vm_2(
    namespace,
    unprivileged_client,
    golden_image_data_source_scope_class,
    tainted_all_nodes_but_one,
):

    with VirtualMachineForTestsFromTemplate(
        name="migration-vm-2",
        labels=Template.generate_template_labels(**RHEL_LATEST_LABELS),
        namespace=namespace.name,
        client=unprivileged_client,
        data_source=golden_image_data_source_scope_class,
    ) as vm:
        running_vm(vm=vm)
        for editor in tainted_all_nodes_but_one:
            editor.restore()
        yield vm


@pytest.fixture(scope="module")
def virt_handler_pods_with_migration_network(
    admin_client, hco_namespace, dedicated_migration_network_hco_config
):
    return get_virt_handler_pods(client=admin_client, namespace=hco_namespace)


@pytest.fixture()
def restarted_migration_vm_1(migration_vm_1):
    # restart VM to get new VMI uid
    migration_vm_1.restart(wait=True)
    running_vm(vm=migration_vm_1)
    return migration_vm_1


@pytest.fixture()
def vms_deployed_on_same_node(migration_vm_1, migration_vm_2):
    vm_source_node_1 = migration_vm_1.vmi.node
    vm_source_node_2 = migration_vm_2.vmi.node
    # To check concurrent VM migration via dedicated network, VMs should be on same node
    assert (
        vm_source_node_1.name == vm_source_node_2.name
    ), f"VMs should be on same node! VM1 node: {vm_source_node_1.name}, VM2 node: {vm_source_node_2.name}"
    return vm_source_node_1


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class",
    [
        pytest.param(
            {
                "dv_name": "dv-migration-vm-rhel",
                "image": RHEL_LATEST["image_path"],
                "storage_class": py_config["default_storage_class"],
                "dv_size": RHEL_LATEST["dv_size"],
            },
        ),
    ],
    indirect=True,
)
@pytest.mark.usefixtures("skip_when_one_node", "skip_if_no_multinic_nodes")
class TestDedicatedLiveMigrationNetwork:
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::migrate_vm")
    @pytest.mark.polarion("CNV-7877")
    def test_migrate_vm_via_dedicated_network(
        self,
        cluster_cpu_model_scope_module,
        utility_pods,
        migration_interface,
        virt_handler_pods_with_migration_network,
        migration_vm_1,
    ):
        source_node = migration_vm_1.vmi.node
        with run_tcpdump_on_source_node(
            utility_pods=utility_pods,
            node=source_node,
            iface_name=migration_interface,
        ):
            migrate_vm_and_verify(vm=migration_vm_1)
            assert_vm_migrated_through_dedicated_network_with_tcpdump(
                utility_pods=utility_pods, node=source_node, vm=migration_vm_1
            )
            assert_vm_migrated_through_dedicated_network_with_logs(
                source_node=source_node,
                vm=migration_vm_1,
                virt_handler_pods=virt_handler_pods_with_migration_network,
            )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::migrate_vm"])
    @pytest.mark.polarion("CNV-7881")
    def test_migrate_multiple_vms_via_dedicated_network(
        self,
        virt_handler_pods_with_migration_network,
        restarted_migration_vm_1,
        migration_vm_2,
        vms_deployed_on_same_node,
    ):
        # Migration is checked only with virt-handler logs
        # TCPDUMP check not used because there is no way to know which vm
        # is migrating through network
        source_node = vms_deployed_on_same_node

        migrate_and_verify_multi_vms(vm_list=[restarted_migration_vm_1, migration_vm_2])
        for vm in [restarted_migration_vm_1, migration_vm_2]:
            assert_vm_migrated_through_dedicated_network_with_logs(
                source_node=source_node,
                vm=vm,
                virt_handler_pods=virt_handler_pods_with_migration_network,
            )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::migrate_vm"])
    @pytest.mark.polarion("CNV-7880")
    def test_drain_node_with_secondary_network(
        self,
        admin_client,
        virt_handler_pods_with_migration_network,
        restarted_migration_vm_1,
    ):
        # Migration is checked only with virt-handler logs
        # TCPDUMP check not used due to possibility that utility-pod
        # might be killed before vm migration
        assert_node_drain_and_vm_migration(
            dyn_client=admin_client,
            vm=restarted_migration_vm_1,
            virt_handler_pods=virt_handler_pods_with_migration_network,
        )