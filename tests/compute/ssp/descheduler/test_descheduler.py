import logging
import re
from bisect import bisect
from collections import Counter

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
from pytest_testconfig import py_config

from tests.compute.utils import (
    fetch_processid_from_linux_vm,
    start_and_fetch_processid_on_linux_vm,
)
from utilities.constants import (
    TIMEOUT_1MIN,
    TIMEOUT_3MIN,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    TIMEOUT_10MIN,
    TIMEOUT_15MIN,
)
from utilities.infra import create_ns, get_pods
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    node_mgmt_console,
    running_vm,
    wait_for_node_schedulable_status,
)


pytestmark = [pytest.mark.tier3]

LOGGER = logging.getLogger(__name__)
DESCHEDULER_POD_LABEL = "app=descheduler"
DESCHEDULER_SUB_NAME = "cluster-kube-descheduler-operator"
RUNNING_PROCESS_NAME_IN_VM = "ping"


class UnexpectedBehaviorError(Exception):
    def __init__(self, error_msg):
        self.error_msg = error_msg

    def __str__(self):
        return f"Unexpected behavior: {self.error_msg}"


class VirtualMachineForDeschedulerTest(VirtualMachineForTests):
    def __init__(self, name, namespace, memory_requests, client, cpu_model):
        super().__init__(
            name=name,
            namespace=namespace,
            client=client,
            memory_requests=memory_requests,
            eviction=True,
            cpu_model=cpu_model,
        )

    def to_dict(self):
        self.body = fedora_vm_body(name=self.name)
        res = super().to_dict()
        metadata = res["spec"]["template"]["metadata"]
        metadata.setdefault("annotations", {})
        metadata["annotations"].update(
            {"descheduler.alpha.kubernetes.io/evict": "true"}
        )
        return res


def calculate_vm_deployment(workers_free_memory):
    """
    Calculate how many VMs with how much RAM should be deployed for test.
    The idea is to have all nodes loaded enough (RAM wise) so that after draining one node
    the remaining will be at ~90% load.

    Args:
        workers_free_memory (dict): dict of total available free memory values on worker nodes
                                    {"<nodename>": <class 'bitmath.GiB'>}

    Returns:
        tuple: (amount of vms to deploy, vm memory requests value)
    """

    def _get_vm_memory_value():
        breakpoints = [20, 50, 400, 8000]
        memory_values = ["1Gi", "2Gi", "10Gi", "80Gi"]
        return memory_values[bisect(breakpoints, vm_amount)]

    # TODO: Calculations should be refined
    # Total free memory value of OS is higher than resources available to OCP node
    # ocp_node_memory_ratio is used to adjust output of "free" command
    ocp_node_memory_ratio = 0.6
    node_amount = len(workers_free_memory)
    assert node_amount >= 2, "Test should run on cluster with 2+ worker nodes"
    total_free = sum(workers_free_memory.values()) * ocp_node_memory_ratio
    vm_amount = round(total_free / node_amount * (node_amount - 1))
    vm_memory = _get_vm_memory_value()
    # adjust vm amount based on value of memory configured for them
    # "-1" is used to ensure the new amount will fit the cluster memory capacity
    # (sometimes cluster mem usage is so tight that last vm is not able to schedule)
    vm_adjusted_amount = round(vm_amount / int(vm_memory[:-2])) - 1

    return vm_adjusted_amount, vm_memory


def wait_vmi_failover(vm, orig_node):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_15MIN, sleep=TIMEOUT_5SEC, func=lambda: vm.vmi.node.name
    )
    LOGGER.info(f"Waiting for {vm.name} to be moved from node {orig_node.name}")
    try:
        for sample in samples:
            if sample and sample != orig_node.name:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"VM {vm.name} failed to deploy on new node")
        raise


def verify_running_process_after_failover(vms_list, process_dict):
    LOGGER.info(f"Verify {RUNNING_PROCESS_NAME_IN_VM} is running after migrations.")
    failed_vms = []
    for vm in vms_list:
        vm_name = vm.name
        if (
            fetch_processid_from_linux_vm(
                vm=vm, process_name=RUNNING_PROCESS_NAME_IN_VM
            )
            != process_dict[vm_name]
        ):
            failed_vms.append(vm_name)

    assert (
        not failed_vms
    ), f"The following VMs process ID has changed after migration: {failed_vms}"


def verify_vms_distribution_after_failover(vms, nodes):
    def _get_vms_per_nodes():
        return vms_per_nodes(vms=vm_nodes(vms=vms))

    LOGGER.info("Verify that each node has at least one VM running on it.")
    sample = None
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_5SEC,
        func=_get_vms_per_nodes,
    )
    try:
        for sample in samples:
            if all([num_vms > 0 for num_vms in sample.values()]) and len(sample) == len(
                nodes
            ):
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Some nodes do not have running VMs: {sample}")
        raise


def wait_pod_deploy(client, namespace, label):
    """
    Waits the pod to be created and running.
    """
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_3MIN,
        sleep=TIMEOUT_5SEC,
        func=get_pods,
        dyn_client=client,
        namespace=namespace,
        label=label,
    )
    try:
        for sample in samples:
            if sample:
                pod = sample[0]
                pod.wait_for_status(status=pod.Status.RUNNING)
                return
    except TimeoutExpiredError:
        LOGGER.error("Descheduler operator deployment failed")
        raise


def vms_per_nodes(vms):
    """
    Args:
        vms (dict): dict of VM objects

    Returns:
        dict: keys - node names, values - number of running VMs
    """
    return Counter([node.name for node in vms.values()])


def vm_nodes(vms):
    """
    Args:
        vms (list): list of VM objects

    Returns:
        dict: keys- VM names, keys - running VMs nodes objects
    """
    return {vm.name: vm.vmi.node for vm in vms}


@pytest.fixture(scope="class")
def skip_if_1tb_memory_or_more_node(workers_free_memory):
    """
    One of QE BM setups has worker with 5 TiB RAM memory while rest workers
    has 120 GiB RAM. Test should be skipped on this cluster, since all VMs will
    always land on 5 TiB RAM and descheduler will not do anything
    """
    for memory in workers_free_memory.values():
        if memory > 1024:
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
    marketplace_ns = py_config["marketplace_namespace"]
    with Subscription(
        name=DESCHEDULER_SUB_NAME,
        namespace=descheduler_ns.name,
        source="redhat-operators",
        source_namespace=marketplace_ns,
        channel=PackageManifest(
            name=DESCHEDULER_SUB_NAME, namespace=marketplace_ns
        ).instance.status.defaultChannel,
    ):
        wait_pod_deploy(
            client=admin_client,
            namespace=descheduler_ns,
            label="name=descheduler-operator",
        )
        yield


@pytest.fixture(scope="class")
def installed_descheduler(admin_client, descheduler_ns, installed_descheduler_sub):
    with KubeDescheduler(
        name="cluster",
        namespace=descheduler_ns.name,
        profiles=["LifecycleAndUtilization"],
        descheduling_interval=TIMEOUT_3MIN,
    ) as kd:
        wait_pod_deploy(
            client=admin_client, namespace=descheduler_ns, label=DESCHEDULER_POD_LABEL
        )
        yield kd


@pytest.fixture(scope="class")
def downsscaled_descheduler_operator_deployment(admin_client, installed_descheduler):
    deployment_name = "descheduler-operator"
    LOGGER.info(
        f"Scale {deployment_name} to 0 is a W/A to force descheduler to use threasholds from config map"
    )
    scale_descheduler_deployment(
        installed_descheduler=installed_descheduler,
        deployment_name=deployment_name,
        replica_count=0,
    )


@pytest.fixture()
def downsscaled_descheduler_cluster_deployment(admin_client, installed_descheduler):
    deployment_name = "cluster"
    LOGGER.info(f"Scale down descheduler {deployment_name} deployment to stop its work")
    scale_descheduler_deployment(
        installed_descheduler=installed_descheduler,
        deployment_name=deployment_name,
        replica_count=0,
    )


@pytest.fixture(scope="class")
def updated_descheduler_policy(
    installed_descheduler, downsscaled_descheduler_operator_deployment
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
        # allocatable.memory format does not include the Bytes suffix(e.g: 23514144Ki)
        nodes_memory[node.name] = bitmath.parse_string_unsafe(
            node.instance.status.allocatable.memory
        ).to_GiB()
        LOGGER.info(
            f"Node {node.name} has {nodes_memory[node.name]} GiB of free memory"
        )
    return dict(sorted(nodes_memory.items(), key=lambda item: item[1]))


@pytest.fixture(scope="class")
def deployed_vms(
    namespace, unprivileged_client, workers_free_memory, nodes_common_cpu_model
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


@pytest.fixture()
def vms_orig_nodes(deployed_vms):
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
    schedulable_nodes, vms_orig_nodes, descheduler_pod, workers_free_memory
):
    """
    Find most suitable node to drain. Search criteria:
      - should be smallest node (RAM wise)
      - should not host descheduler operator pod
      - should host at least 1 VM
    """

    schedulable_nodes_dict = {node.name: node for node in schedulable_nodes}
    vm_per_node_counters = vms_per_nodes(vms=vms_orig_nodes)

    for node in workers_free_memory:
        if node != descheduler_pod.node.name and vm_per_node_counters[node] >= 1:
            return schedulable_nodes_dict[node]

    raise ValueError("No suitable node to drain")


@pytest.fixture()
def drain_node(deployed_vms, vms_orig_nodes, node_to_drain):
    with node_mgmt_console(node=node_to_drain, node_mgmt="drain"):
        wait_for_node_schedulable_status(node=node_to_drain, status=False)
        for vm in deployed_vms:
            if vms_orig_nodes[vm.name].name == node_to_drain.name:
                wait_vmi_failover(vm=vm, orig_node=vms_orig_nodes[vm.name])


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
                pdb.name: pdb.instance.spec.minAvailable
                for pdb in sample
                if pdb.instance.spec.minAvailable > 1
            }
            # Return if there are no more required migrations
            if not pdbs_desired_states:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Some migrations are still created: {pdbs_desired_states}")
        raise


def verify_vms_consistent_virt_launcher_pods(running_vms):
    """Verify VMs virt launcher pods are not replaced (sampled every one minute).

    Using VMs virt launcher pods to verify that VMs are not migrated nor restarted.

    Args:
        running_vms (list): list of VMs
    """

    def _vms_launcher_pods():
        return {
            vm.name: vm.vmi.virt_launcher_pod
            for vm in running_vms
            if vm.vmi.virt_launcher_pod.status
            == vm.vmi.virt_launcher_pod.Status.RUNNING
        }

    orig_virt_launcher_pods = _vms_launcher_pods()
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=TIMEOUT_1MIN,
        func=_vms_launcher_pods,
    )
    try:
        for sample in samples:
            if any(
                [
                    pod.name != orig_virt_launcher_pods[vm].name
                    for vm, pod in sample.items()
                ]
            ):
                raise UnexpectedBehaviorError(
                    error_msg=f"Some VMs were migrated: {sample}"
                )

    except TimeoutExpiredError:
        LOGGER.info("No VMs were migrated.")


def scale_descheduler_deployment(installed_descheduler, deployment_name, replica_count):
    """Scale descheduler deployment and wait until all replicas are updated"""
    descheduler_deployment = Deployment(
        name=deployment_name, namespace=installed_descheduler.namespace
    )
    descheduler_deployment.scale_replicas(replica_count=replica_count)
    descheduler_deployment.wait_for_replicas(
        deployed=True if replica_count > 0 else False
    )


@pytest.mark.usefixtures(
    "skip_if_1tb_memory_or_more_node",
    "skip_when_one_node",
)
class TestDeschduler:
    @pytest.mark.dependency(name="test_descheduler")
    @pytest.mark.polarion("CNV-5922")
    def test_descheduler(
        self,
        updated_descheduler,
        descheduler_pod,
        deployed_vms,
        vms_started_process,
        node_to_drain,
        drain_node,
        schedulable_nodes,
    ):
        verify_running_process_after_failover(
            vms_list=deployed_vms, process_dict=vms_started_process
        )
        verify_vms_distribution_after_failover(
            vms=deployed_vms, nodes=schedulable_nodes
        )

    @pytest.mark.dependency(depends=["test_descheduler"])
    @pytest.mark.polarion("CNV-7316")
    def test_no_migrations_storm(
        self,
        deployed_vms,
        downsscaled_descheduler_cluster_deployment,
        completed_migrations,
    ):
        LOGGER.info(
            "Verify no migration storm after triggered migrations by the descheduler."
        )
        verify_vms_consistent_virt_launcher_pods(running_vms=deployed_vms)
