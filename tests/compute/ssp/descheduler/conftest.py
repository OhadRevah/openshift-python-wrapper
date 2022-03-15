import logging
import re

import bitmath
import pytest
from ocp_resources.configmap import ConfigMap
from ocp_resources.deployment import Deployment
from ocp_resources.kube_descheduler import KubeDescheduler
from ocp_resources.operator_group import OperatorGroup
from ocp_resources.package_manifest import PackageManifest
from ocp_resources.pod_disruption_budget import PodDisruptionBudget
from ocp_resources.resource import ResourceEditor
from ocp_resources.subscription import Subscription
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from ocp_resources.virtual_machine_instance_migration import (
    VirtualMachineInstanceMigration,
)
from openshift.dynamic.exceptions import NotFoundError
from pytest_testconfig import py_config

from tests.compute.ssp.descheduler.constants import (
    DESCHEDULING_INTERVAL_120SEC,
    RUNNING_PROCESS_NAME_IN_VM,
)
from tests.compute.ssp.descheduler.utils import (
    VirtualMachineForDeschedulerTest,
    calculate_vm_deployment,
    has_kubevirt_owner,
    vm_nodes,
    vms_per_nodes,
    wait_vmi_failover,
)
from tests.compute.utils import (
    scale_deployment_replicas,
    start_and_fetch_processid_on_linux_vm,
)
from utilities.constants import TIMEOUT_5MIN
from utilities.infra import create_ns, get_pods, is_bug_open
from utilities.virt import (
    node_mgmt_console,
    running_vm,
    wait_for_node_schedulable_status,
)


LOGGER = logging.getLogger(__name__)
DESCHEDULER_POD_LABEL = "app=descheduler"


@pytest.fixture(scope="class")
def skip_if_1tb_memory_or_more_node(workers_free_memory):
    """
    One of QE BM setups has worker with 5 TiB RAM memory while rest workers
    has 120 GiB RAM. Test should be skipped on this cluster, since all VMs will
    always land on 5 TiB RAM and descheduler will not do anything
    """
    for memory in workers_free_memory.values():
        if memory > bitmath.TiB(value=1):
            pytest.skip("Cluster has node with more than 1 TiB RAM")


@pytest.fixture(scope="class")
def descheduler_ns(admin_client):
    yield from create_ns(
        admin_client=admin_client, name="openshift-kube-descheduler-operator"
    )


@pytest.fixture(scope="class")
def installed_descheduler_og(descheduler_ns):
    with OperatorGroup(
        name="descheduler-operator-group",
        namespace=descheduler_ns.name,
        target_namespaces=[descheduler_ns.name],
    ):
        yield


@pytest.fixture(scope="class")
def installed_descheduler_sub(admin_client, descheduler_ns, installed_descheduler_og):
    descheduler_sub_name = "cluster-kube-descheduler-operator"
    marketplace_ns = py_config["marketplace_namespace"]
    with Subscription(
        name=descheduler_sub_name,
        namespace=descheduler_ns.name,
        source="redhat-operators",
        source_namespace=marketplace_ns,
        channel=PackageManifest(
            name=descheduler_sub_name, namespace=marketplace_ns
        ).instance.status.defaultChannel,
    ):
        Deployment(
            name="descheduler-operator", namespace=descheduler_ns.name
        ).wait_for_replicas()
        yield


@pytest.fixture(scope="class")
def installed_descheduler(admin_client, descheduler_ns, installed_descheduler_sub):
    kube_descheduler_name = "cluster"
    with KubeDescheduler(
        name=kube_descheduler_name,
        namespace=descheduler_ns.name,
        profiles=["LifecycleAndUtilization"],
        descheduling_interval=DESCHEDULING_INTERVAL_120SEC,
    ) as kd:
        Deployment(
            name=kube_descheduler_name, namespace=descheduler_ns.name
        ).wait_for_replicas()
        yield kd


@pytest.fixture(scope="class")
def downscaled_descheduler_operator_deployment(admin_client, descheduler_ns):
    deployment_name = "descheduler-operator"
    LOGGER.info(
        f"Scale {deployment_name} to 0 is a W/A to force descheduler to use threasholds from config map"
    )
    with scale_deployment_replicas(
        deployment_name=deployment_name,
        namespace=descheduler_ns.name,
        replica_count=0,
    ):
        yield


@pytest.fixture()
def downscaled_descheduler_cluster_deployment(admin_client, descheduler_ns):
    deployment_name = "cluster"
    LOGGER.info(f"Scale down descheduler {deployment_name} deployment to stop its work")
    with scale_deployment_replicas(
        deployment_name=deployment_name,
        namespace=descheduler_ns.name,
        replica_count=0,
    ):
        yield


@pytest.fixture(scope="class")
def updated_descheduler_policy(
    installed_descheduler, downscaled_descheduler_operator_deployment
):
    policy_yaml_name = "policy.yaml"
    cm = ConfigMap(
        name=installed_descheduler.name, namespace=installed_descheduler.namespace
    )
    threshold_data = re.search(
        r"targetThresholds\D*(.*?)\D*?thresholdPriority",
        cm.instance["data"][policy_yaml_name],
        re.DOTALL,
    ).group(1)
    new_thresholds = (
        "60\n          memory: 80\n          pods: 100\n        thresholds:"
        "\n          cpu: 30\n          memory: 50\n          pods: 30"
    )
    ResourceEditor(
        patches={
            cm: {
                "data": {
                    policy_yaml_name: re.sub(
                        threshold_data,
                        new_thresholds,
                        cm.instance["data"]["policy.yaml"],
                    )
                }
            }
        }
    ).update()


@pytest.fixture(scope="class")
def updated_descheduler(admin_client, descheduler_ns, updated_descheduler_policy):
    get_pods(
        dyn_client=admin_client, namespace=descheduler_ns, label=DESCHEDULER_POD_LABEL
    )[
        0
    ].clean_up()  # apply cm update


@pytest.fixture(scope="class")
def workers_free_memory(schedulable_nodes, utility_pods):
    nodes_memory = {}
    for node in schedulable_nodes:
        # memory format does not include the Bytes suffix(e.g: 23514144Ki)
        memory = getattr(
            node.instance.status.allocatable,
            "memory",
            node.instance.status.capacity.memory,
        )
        nodes_memory[node.name] = bitmath.parse_string_unsafe(s=memory).to_GiB()
        LOGGER.info(f"Node {node.name} has {nodes_memory[node.name]} of free memory")
    return dict(sorted(nodes_memory.items(), key=lambda item: item[1]))


@pytest.fixture(scope="class")
def deployed_vms(
    admin_client,
    namespace,
    unprivileged_client,
    workers_free_memory,
    nodes_common_cpu_model,
):
    vms = []
    vm_amount, vm_memory = calculate_vm_deployment(
        workers_free_memory=workers_free_memory
    )
    LOGGER.info(f"Deploying {vm_amount} VMs, each with {vm_memory} RAM")
    for index in range(1, vm_amount):
        deployed_vm = VirtualMachineForDeschedulerTest(
            name=f"vm-{index}",
            namespace=namespace.name,
            client=unprivileged_client,
            memory_requests=vm_memory,
            cpu_model=nodes_common_cpu_model,
        )
        deployed_vm.deploy()
        deployed_vm.start()
        vms.append(deployed_vm)

    for vm in vms:
        running_vm(vm=vm)

    yield vms

    for vm in vms:
        vm.clean_up()

    # TODO: Remove finzalizer from VMIM to unblock deletion
    if is_bug_open(bug_id=2040377):
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
            except NotFoundError:
                LOGGER.info(
                    f"VirtualMachineInstanceMigration {migration_job.name} is already deleted."
                )


@pytest.fixture(scope="class")
def vms_orig_nodes_before_node_drain(deployed_vms):
    return vm_nodes(vms=deployed_vms)


@pytest.fixture()
def vms_started_process(deployed_vms):
    vms_process_id_dict = {}
    for vm in deployed_vms:
        vms_process_id_dict[vm.name] = start_and_fetch_processid_on_linux_vm(
            vm=vm, process_name=RUNNING_PROCESS_NAME_IN_VM, args="localhost"
        )

    return vms_process_id_dict


@pytest.fixture()
def descheduler_pod(admin_client, descheduler_ns):
    return get_pods(
        dyn_client=admin_client, namespace=descheduler_ns, label=DESCHEDULER_POD_LABEL
    )[0]


@pytest.fixture()
def node_to_drain(
    schedulable_nodes,
    vms_orig_nodes_before_node_drain,
    descheduler_pod,
    workers_free_memory,
):
    """
    Find most suitable node to drain. Search criteria:
      - should be smallest node (RAM wise)
      - should not host descheduler operator pod
      - should host at least 1 VM
    """

    schedulable_nodes_dict = {node.name: node for node in schedulable_nodes}
    vm_per_node_counters = vms_per_nodes(vms=vms_orig_nodes_before_node_drain)

    for node in workers_free_memory:
        if node != descheduler_pod.node.name and vm_per_node_counters[node] >= 1:
            return schedulable_nodes_dict[node]

    raise ValueError("No suitable node to drain")


@pytest.fixture()
def drain_uncordon_node(
    deployed_vms,
    vms_orig_nodes_before_node_drain,
    node_to_drain,
):
    """Return when node is schedulable again after uncordon"""
    with node_mgmt_console(node=node_to_drain, node_mgmt="drain"):
        wait_for_node_schedulable_status(node=node_to_drain, status=False)
        for vm in deployed_vms:
            if vms_orig_nodes_before_node_drain[vm.name].name == node_to_drain.name:
                wait_vmi_failover(
                    vm=vm, orig_node=vms_orig_nodes_before_node_drain[vm.name]
                )


@pytest.fixture()
def completed_migrations(admin_client, namespace):
    """Verify VMs PodDisruptionBudgets are not updated to start migrations.

    Check that once deschduler cluster deployment is scaled down to 0 all VMs have 1 as the desired number of pods.
    Having a desired state greater than 1 for a VM (i.e its virt-launcher pod) leads to VM migration.
    """
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=10,
        func=lambda: list(
            PodDisruptionBudget.get(
                dyn_client=admin_client,
                namespace=namespace.name,
            )
        ),
    )
    pdbs_desired_states = None
    try:
        for sample in samples:
            pdbs_desired_states = {
                pod_disruption_budget.name: pod_disruption_budget.instance.spec.minAvailable
                for pod_disruption_budget in sample
                if has_kubevirt_owner(resource=pod_disruption_budget)
                and pod_disruption_budget.instance.spec.minAvailable > 1
            }

            # Return if there are no more required migrations
            if not pdbs_desired_states:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Some migrations are still created: {pdbs_desired_states}")
        raise
