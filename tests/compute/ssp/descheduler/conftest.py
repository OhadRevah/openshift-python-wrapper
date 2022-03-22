import collections
import logging

import bitmath
import pytest
from ocp_resources.deployment import Deployment
from ocp_resources.kube_descheduler import KubeDescheduler
from ocp_resources.namespace import Namespace
from ocp_resources.operator_group import OperatorGroup
from ocp_resources.pod import Pod
from ocp_resources.resource import ResourceEditor
from ocp_resources.subscription import Subscription
from ocp_resources.virtual_machine_instance_migration import (
    VirtualMachineInstanceMigration,
)
from openshift.dynamic.exceptions import NotFoundError, ResourceNotFoundError

from tests.compute.ssp.descheduler.constants import (
    DESCHEDULING_INTERVAL_120SEC,
    RUNNING_PING_PROCESS_NAME_IN_VM,
)
from tests.compute.ssp.descheduler.utils import (
    calculate_vm_deployment,
    deploy_vms,
    get_allocatable_memory_per_node,
    get_descheduler_pod,
    get_pod_memory_requests,
    install_profile_strategies,
    start_vms_with_process,
    vm_nodes,
    vms_per_nodes,
    wait_vmi_failover,
)
from tests.compute.utils import check_pod_disruption_budget_for_completed_migrations
from utilities.infra import (
    create_ns,
    get_raw_package_manifest,
    scale_deployment_replicas,
)
from utilities.virt import node_mgmt_console, wait_for_node_schedulable_status


LOGGER = logging.getLogger(__name__)

DESCHEDULER_OPERATOR_DEPLOYMENT_NAME = "descheduler-operator"
DEPLOYMENT_SIZE = {
    "cpu": "500m",
    "memory": bitmath.GiB(value=2),
}


@pytest.fixture(scope="module")
def skip_if_1tb_memory_or_more_node(allocatable_memory_per_node_scope_module):
    """
    One of QE BM setups has worker with 5 TiB RAM memory while rest workers
    has 120 GiB RAM. Test should be skipped on this cluster.
    """
    upper_memory_limit = bitmath.TiB(value=1)
    for node, memory in allocatable_memory_per_node_scope_module.items():
        if memory >= upper_memory_limit:
            pytest.skip(
                f"Cluster has node with at least {upper_memory_limit} RAM: {node.name}"
            )


@pytest.fixture(scope="module")
def descheduler_ns(admin_client):
    yield from create_ns(
        admin_client=admin_client,
        name="openshift-kube-descheduler-operator",
    )


@pytest.fixture(scope="module")
def installed_descheduler_og(descheduler_ns):
    with OperatorGroup(
        name="descheduler-operator-group",
        namespace=descheduler_ns.name,
        target_namespaces=[descheduler_ns.name],
    ):
        yield


@pytest.fixture(scope="module")
def installed_descheduler_sub(admin_client, descheduler_ns, installed_descheduler_og):
    descheduler_sub_name = "cluster-kube-descheduler-operator"
    catalog_source = "redhat-operators"
    raw_package_manifest = get_raw_package_manifest(
        admin_client=admin_client,
        name=descheduler_sub_name,
        catalog_source=catalog_source,
    )

    with Subscription(
        name=descheduler_sub_name,
        namespace=descheduler_ns.name,
        source=catalog_source,
        source_namespace=raw_package_manifest.metadata.namespace,
        channel=raw_package_manifest.status.defaultChannel,
    ):
        Deployment(
            name=DESCHEDULER_OPERATOR_DEPLOYMENT_NAME, namespace=descheduler_ns.name
        ).wait_for_replicas()
        yield


@pytest.fixture(scope="module")
def installed_descheduler(admin_client, descheduler_ns, installed_descheduler_sub):
    descheduler_deployment_name = "cluster"
    with KubeDescheduler(
        name=descheduler_deployment_name,
        namespace=descheduler_ns.name,
        profiles=["DevPreviewLongLifecycle"],
        descheduling_interval=DESCHEDULING_INTERVAL_120SEC,
    ) as kd:
        Deployment(
            name=descheduler_deployment_name, namespace=descheduler_ns.name
        ).wait_for_replicas()
        yield kd


@pytest.fixture(scope="class")
def downscaled_descheduler_operator_deployment(installed_descheduler):
    LOGGER.info(
        f"Scale {DESCHEDULER_OPERATOR_DEPLOYMENT_NAME} to 0 "
        "is a W/A to force descheduler to use thresholds from config map"
    )
    with scale_deployment_replicas(
        deployment_name=DESCHEDULER_OPERATOR_DEPLOYMENT_NAME,
        namespace=installed_descheduler.namespace,
        replica_count=0,
    ):
        yield


@pytest.fixture(scope="class")
def downscaled_descheduler_cluster_deployment(admin_client, installed_descheduler):
    LOGGER.info(
        f"Scale down descheduler {installed_descheduler.name} deployment to stop its work"
    )
    with scale_deployment_replicas(
        deployment_name=installed_descheduler.name,
        namespace=installed_descheduler.namespace,
        replica_count=0,
    ):
        yield


@pytest.fixture(scope="module")
def allocatable_memory_per_node_scope_module(schedulable_nodes):
    return get_allocatable_memory_per_node(schedulable_nodes=schedulable_nodes)


@pytest.fixture(scope="class")
def allocatable_memory_per_node_scope_class(schedulable_nodes):
    return get_allocatable_memory_per_node(schedulable_nodes=schedulable_nodes)


@pytest.fixture(scope="class")
def available_nodes_without_descheduler_pod(
    admin_client,
    installed_descheduler,
    available_memory_per_node,
):
    descheduler_pod = get_descheduler_pod(
        admin_client=admin_client,
        namespace=Namespace(name=installed_descheduler.namespace),
    )
    return [
        node
        for node in available_memory_per_node
        if node.name != descheduler_pod.node.name
    ]


@pytest.fixture(scope="class")
def calculated_vm_deployment_without_descheduler_node(
    request,
    admin_client,
    descheduler_ns,
    available_memory_per_node,
    available_nodes_without_descheduler_pod,
):
    yield calculate_vm_deployment(
        available_memory_per_node=available_memory_per_node,
        deployment_size=DEPLOYMENT_SIZE,
        available_nodes=available_nodes_without_descheduler_pod,
        percent_of_available_memory=request.param,
    )


@pytest.fixture(scope="class")
def deployed_vms_calculated_without_descheduler_node(
    namespace,
    admin_client,
    unprivileged_client,
    nodes_common_cpu_model,
    available_memory_per_node,
    calculated_vm_deployment_without_descheduler_node,
):
    yield from deploy_vms(
        client=unprivileged_client,
        namespace_name=namespace.name,
        cpu_model=nodes_common_cpu_model,
        vm_count=sum(calculated_vm_deployment_without_descheduler_node.values()),
        deployment_size=DEPLOYMENT_SIZE,
        descheduler_eviction=True,
    )

    # Remove finalizer from remaining VMIM to ensure deletion
    for migration_job in VirtualMachineInstanceMigration.get(
        dyn_client=admin_client, namespace=namespace.name
    ):
        try:
            migration_job_dict = migration_job.instance.to_dict()
            migration_job_dict["metadata"].pop("finalizers", None)
            ResourceEditor(
                patches={migration_job: migration_job_dict},
                action="replace",
            ).update()
            migration_job.wait_deleted()
        except (NotFoundError, ResourceNotFoundError):
            LOGGER.info(
                f"VirtualMachineInstanceMigration {migration_job.name} is already deleted."
            )


@pytest.fixture(scope="class")
def vms_orig_nodes_before_node_drain(deployed_vms_calculated_without_descheduler_node):
    return vm_nodes(vms=deployed_vms_calculated_without_descheduler_node)


@pytest.fixture()
def vms_started_process_for_node_drain(
    deployed_vms_calculated_without_descheduler_node,
):
    return start_vms_with_process(
        vms=deployed_vms_calculated_without_descheduler_node,
        process_name=RUNNING_PING_PROCESS_NAME_IN_VM,
        args="localhost",
    )


@pytest.fixture(scope="class")
def node_to_drain(
    admin_client,
    schedulable_nodes,
    installed_descheduler,
    vms_orig_nodes_before_node_drain,
):
    """
    Find most suitable node to drain. Search criteria:
      - should not host descheduler operator pod
      - should host at least 1 VM
    """

    vm_per_node_counters = vms_per_nodes(vms=vms_orig_nodes_before_node_drain)
    descheduler_pod = get_descheduler_pod(
        admin_client=admin_client,
        namespace=Namespace(name=installed_descheduler.namespace),
    )
    for node in schedulable_nodes:
        if (
            node.name != descheduler_pod.node.name
            and vm_per_node_counters[node.name] > 0
        ):
            return node

    raise ValueError("No suitable node to drain")


@pytest.fixture()
def drain_uncordon_node(
    deployed_vms_calculated_without_descheduler_node,
    vms_orig_nodes_before_node_drain,
    node_to_drain,
):
    """Return when node is schedulable again after uncordon"""
    with node_mgmt_console(node=node_to_drain, node_mgmt="drain"):
        wait_for_node_schedulable_status(node=node_to_drain, status=False)
        for vm in deployed_vms_calculated_without_descheduler_node:
            if vms_orig_nodes_before_node_drain[vm.name].name == node_to_drain.name:
                wait_vmi_failover(
                    vm=vm, orig_node=vms_orig_nodes_before_node_drain[vm.name]
                )


@pytest.fixture()
def completed_migrations(admin_client, namespace):
    check_pod_disruption_budget_for_completed_migrations(
        admin_client=admin_client, namespace=namespace.name
    )


@pytest.fixture(scope="class")
def updated_profile_strategy_static_low_node_utilization_for_node_drain(
    installed_descheduler,
    downscaled_descheduler_operator_deployment,
    static_strategy_low_node_utilization_for_node_drain,
):
    with install_profile_strategies(
        installed_descheduler=installed_descheduler,
        strategies=static_strategy_low_node_utilization_for_node_drain,
    ):
        yield


@pytest.fixture(scope="class")
def static_strategy_low_node_utilization_for_node_drain():
    return {
        "LowNodeUtilization": {
            "enabled": True,
            "params": {
                "nodeResourceUtilizationThresholds": {
                    "thresholds": {
                        "cpu": 99,
                        "memory": 50,
                        "pods": 99,
                    },
                    "targetThresholds": {
                        "cpu": 100,
                        "memory": 80,
                        "pods": 100,
                    },
                }
            },
        }
    }


@pytest.fixture(scope="class")
def non_terminated_pods_per_node(admin_client, schedulable_nodes):
    return {
        node: list(
            Pod.get(
                dyn_client=admin_client,
                field_selector=f"spec.nodeName={node.name},status.phase!=Succeeded,status.phase!=Failed",
            )
        )
        for node in schedulable_nodes
    }


@pytest.fixture(scope="class")
def memory_requests_per_node(schedulable_nodes, non_terminated_pods_per_node):
    memory_requests = collections.defaultdict(bitmath.Byte)
    for node in schedulable_nodes:
        for pod in non_terminated_pods_per_node[node]:
            pod_instance = pod.exists
            if pod_instance:
                memory_requests[node] += get_pod_memory_requests(
                    pod_instance=pod_instance
                )

    return memory_requests


@pytest.fixture(scope="class")
def available_memory_per_node(
    schedulable_nodes,
    allocatable_memory_per_node_scope_class,
    memory_requests_per_node,
):
    return {
        node: allocatable_memory_per_node_scope_class[node]
        - memory_requests_per_node[node]
        for node in schedulable_nodes
    }
