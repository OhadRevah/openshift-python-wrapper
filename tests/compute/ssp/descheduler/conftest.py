import collections
import logging

import bitmath
import pytest
from ocp_resources.deployment import Deployment
from ocp_resources.kube_descheduler import KubeDescheduler
from ocp_resources.namespace import Namespace
from ocp_resources.operator_group import OperatorGroup
from ocp_resources.pod_disruption_budget import PodDisruptionBudget
from ocp_resources.resource import Resource, ResourceEditor
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
    DeploymentForDeschedulerTests,
    assert_state_for_utilization_imbalance,
    calculate_vm_deployment,
    deploy_vms,
    get_allocatable_memory_per_node,
    get_descheduler_pod,
    get_non_terminated_pods,
    get_pod_memory_requests,
    get_strategy_low_node_utilization,
    install_profile_strategies,
    start_vms_with_process,
    vm_nodes,
    vms_per_nodes,
    wait_vmi_failover,
)
from tests.compute.utils import check_pod_disruption_budget_for_completed_migrations
from utilities.constants import TIMEOUT_5SEC
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
LOCALHOST = "localhost"


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
def updated_profile_strategy_static_low_node_utilization_for_utilization_imbalance(
    installed_descheduler,
    downscaled_descheduler_operator_deployment,
    static_strategy_low_node_utilization_for_utilization_imbalance,
):
    with install_profile_strategies(
        installed_descheduler=installed_descheduler,
        strategies=static_strategy_low_node_utilization_for_utilization_imbalance,
    ):
        yield


@pytest.fixture(scope="class")
def static_strategy_low_node_utilization_for_node_drain():
    return get_strategy_low_node_utilization(
        thresholds=dict(
            cpu=99,
            memory=50,
            pods=99,
        ),
        target_thresholds=dict(
            cpu=100,
            memory=80,
            pods=100,
        ),
    )


@pytest.fixture(scope="class")
def static_strategy_low_node_utilization_for_utilization_imbalance():
    return get_strategy_low_node_utilization(
        thresholds=dict(
            cpu=99,
            memory=99,
            pods=50,
        ),
        target_thresholds=dict(
            cpu=100,
            memory=100,
            pods=80,
        ),
    )


@pytest.fixture(scope="class")
def allocatable_pods_per_node(schedulable_nodes, utility_pods):
    allocatable_pods = collections.defaultdict()
    for node in schedulable_nodes:
        node_status = node.instance.to_dict()["status"]
        allocatable_pods[node] = int(
            node_status["allocatable"].get("pods", node_status["capacity"]["pods"])
        )
        LOGGER.info(f"Node {node.name} has {allocatable_pods[node]} allocatable pods")

    return allocatable_pods


@pytest.fixture(scope="class")
def non_terminated_pods_per_node(admin_client, schedulable_nodes):
    return {
        node: get_non_terminated_pods(client=admin_client, node=node)
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


@pytest.fixture(scope="class")
def deployed_evictable_vms_for_utilization_imbalance(
    namespace,
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


@pytest.fixture(scope="class")
def deployed_no_annotation_vms_for_utilization_imbalance(
    namespace,
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
        descheduler_eviction=False,
    )


@pytest.fixture()
def vms_started_process_for_utilization_imbalance(
    deployed_evictable_vms_for_utilization_imbalance,
):
    return start_vms_with_process(
        vms=deployed_evictable_vms_for_utilization_imbalance,
        process_name=RUNNING_PING_PROCESS_NAME_IN_VM,
        args=LOCALHOST,
    )


@pytest.fixture()
def no_annotation_vms_started_process_for_utilization_imbalance(
    deployed_no_annotation_vms_for_utilization_imbalance,
):
    return start_vms_with_process(
        vms=deployed_no_annotation_vms_for_utilization_imbalance,
        process_name=RUNNING_PING_PROCESS_NAME_IN_VM,
        args=LOCALHOST,
    )


@pytest.fixture(scope="class")
def vms_on_low_utilization_nodes(
    deployed_evictable_vms_for_utilization_imbalance, nodes_with_low_pod_utilization
):
    node_names_with_low_pod_utilization = [
        node.name for node in nodes_with_low_pod_utilization
    ]
    return [
        vm
        for vm in deployed_evictable_vms_for_utilization_imbalance
        if vm.vmi.node.name in node_names_with_low_pod_utilization
    ]


@pytest.fixture(scope="class")
def vms_on_nominal_utilization_nodes(
    deployed_evictable_vms_for_utilization_imbalance, nodes_with_nominal_pod_utilization
):
    node_names = [node.name for node in nodes_with_nominal_pod_utilization]
    return [
        vm
        for vm in deployed_evictable_vms_for_utilization_imbalance
        if vm.vmi.node.name in node_names
    ]


@pytest.fixture(scope="class")
def non_descheduler_nodes(admin_client, schedulable_nodes, installed_descheduler):
    descheduler_pod = get_descheduler_pod(
        admin_client=admin_client,
        namespace=Namespace(name=installed_descheduler.namespace),
    )
    return [
        node for node in schedulable_nodes if node.name != descheduler_pod.node.name
    ]


@pytest.fixture(scope="class")
def orig_vms_from_target_node_for_utilization_increase(
    vms_on_low_utilization_nodes,
    vms_on_nominal_utilization_nodes,
    non_descheduler_nodes,
):
    possible_target_vms = (
        vms_on_nominal_utilization_nodes + vms_on_low_utilization_nodes
    )
    non_descheduler_node_names = [node.name for node in non_descheduler_nodes]

    target_vms = []
    target_node = None
    for vm in possible_target_vms:
        if vm.vmi.node.name in non_descheduler_node_names and not target_node:
            target_node = vm.vmi.node

        if target_node and vm.vmi.node.name == target_node.name:
            target_vms.append(vm)

    return target_vms


@pytest.fixture(scope="class")
def target_node_for_utilization_increase(
    orig_vms_from_target_node_for_utilization_increase,
    nodes_with_high_pod_utilization,
    nodes_with_low_pod_utilization,
):
    assert_state_for_utilization_imbalance(
        nodes_with_high_pod_utilization=nodes_with_high_pod_utilization,
        nodes_with_low_pod_utilization=nodes_with_low_pod_utilization,
    )
    target_node = orig_vms_from_target_node_for_utilization_increase[0].vmi.node
    LOGGER.info(f"Target node for utilization increase: {target_node.name}")
    return target_node


@pytest.fixture(scope="class")
def pod_requests_per_node(schedulable_nodes, non_terminated_pods_per_node):
    pod_requests = collections.defaultdict()
    for node in schedulable_nodes:
        pod_requests[node] = 0
        for pod in non_terminated_pods_per_node[node]:
            if pod.exists:
                pod_requests[node] += 1

    return pod_requests


@pytest.fixture(scope="class")
def pod_usage_per_node_scope_class(
    schedulable_nodes,
    allocatable_pods_per_node,
    pod_requests_per_node,
):
    return {
        node: pod_requests_per_node[node] / allocatable_pods_per_node[node]
        for node in schedulable_nodes
    }


@pytest.fixture(scope="class")
def nodes_with_high_pod_utilization(
    pod_usage_per_node_scope_class,
    static_strategy_low_node_utilization_for_utilization_imbalance,
):
    target_thresholds = static_strategy_low_node_utilization_for_utilization_imbalance[
        "LowNodeUtilization"
    ]["params"]["nodeResourceUtilizationThresholds"]["targetThresholds"]

    high_utilization_nodes = []
    for node in pod_usage_per_node_scope_class:
        if pod_usage_per_node_scope_class[node] > target_thresholds["pods"]:
            high_utilization_nodes.append(node)

    return high_utilization_nodes


@pytest.fixture(scope="class")
def node_resource_utilization_thresholds_for_utilization_imbalance(
    static_strategy_low_node_utilization_for_utilization_imbalance,
):
    return static_strategy_low_node_utilization_for_utilization_imbalance[
        "LowNodeUtilization"
    ]["params"]["nodeResourceUtilizationThresholds"]


@pytest.fixture(scope="class")
def nodes_with_nominal_pod_utilization(
    pod_usage_per_node_scope_class,
    node_resource_utilization_thresholds_for_utilization_imbalance,
):
    thresholds = node_resource_utilization_thresholds_for_utilization_imbalance[
        "thresholds"
    ]
    target_thresholds = node_resource_utilization_thresholds_for_utilization_imbalance[
        "targetThresholds"
    ]

    nominal_utilization_nodes = []
    for node in pod_usage_per_node_scope_class:
        pod_value = pod_usage_per_node_scope_class[node]
        if thresholds["pods"] <= pod_value <= target_thresholds["pods"]:
            nominal_utilization_nodes.append(node)

    return nominal_utilization_nodes


@pytest.fixture(scope="class")
def nodes_with_low_pod_utilization(
    pod_usage_per_node_scope_class,
    node_resource_utilization_thresholds_for_utilization_imbalance,
):
    thresholds = node_resource_utilization_thresholds_for_utilization_imbalance[
        "thresholds"
    ]

    low_utilization_nodes = []
    for node in pod_usage_per_node_scope_class:
        if pod_usage_per_node_scope_class[node] < thresholds["pods"]:
            low_utilization_nodes.append(node)

    return low_utilization_nodes


@pytest.fixture(scope="class")
def unallocated_pod_count(
    admin_client,
    target_node_for_utilization_increase,
):
    non_terminated_pod_count = len(
        get_non_terminated_pods(
            client=admin_client, node=target_node_for_utilization_increase
        )
    )
    return (
        int(target_node_for_utilization_increase.instance.status.capacity.pods)
        - non_terminated_pod_count
    )


@pytest.fixture(scope="class")
def utilization_imbalance(
    admin_client,
    namespace,
    target_node_for_utilization_increase,
    unallocated_pod_count,
):
    evict_protected_pod_label_dict = {"test-evict-protected-pod": "true"}
    evict_protected_pod_selector = {"matchLabels": evict_protected_pod_label_dict}

    utilization_imbalance_deployment_name = "utilization-imbalance-deployment"
    with PodDisruptionBudget(
        name=utilization_imbalance_deployment_name,
        namespace=namespace.name,
        min_available=unallocated_pod_count,
        selector=evict_protected_pod_selector,
    ):
        with DeploymentForDeschedulerTests(
            name=utilization_imbalance_deployment_name,
            namespace=namespace.name,
            client=admin_client,
            node_selector_dict={
                f"{Resource.ApiGroup.KUBERNETES_IO}/hostname": target_node_for_utilization_increase.hostname,
            },
            replica_count=unallocated_pod_count,
            pod_selector=evict_protected_pod_selector,
            template_labels=evict_protected_pod_label_dict,
        ) as deployment:
            deployment.wait_for_replicas(timeout=unallocated_pod_count * TIMEOUT_5SEC)
            yield
