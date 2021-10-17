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
from ocp_resources.resource import ResourceEditor
from ocp_resources.subscription import Subscription
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from pytest_testconfig import py_config

from tests.compute.utils import (
    fetch_processid_from_linux_vm,
    start_and_fetch_processid_on_linux_vm,
)
from utilities.constants import TIMEOUT_3MIN, TIMEOUT_5MIN, TIMEOUT_15MIN
from utilities.infra import ExecCommandOnPod, create_ns, get_pods
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

    def _get_vm_memory_value(vm_amount):
        breakpoints = [20, 50, 400, 8000]
        memory_values = ["1Gi", "2Gi", "10Gi", "80Gi"]
        return memory_values[bisect(breakpoints, vm_amount)]

    # Total free memory value of OS is higher than resources available to OCP node
    # ocp_node_memory_ratio is used to adjust output of "free" command
    ocp_node_memory_ratio = 0.8
    node_amount = len(workers_free_memory)
    assert node_amount >= 2, "Test should run on cluster with 2+ worker nodes"
    total_free = sum(workers_free_memory.values()) * ocp_node_memory_ratio
    vm_amount = round(total_free / node_amount * (node_amount - 1))
    vm_memory = _get_vm_memory_value(vm_amount=vm_amount)
    # adjust vm amount based on value of memory configured for them
    # "-1" is used to ensure the new amount will fit the cluster memory capacity
    # (sometimes cluster mem usage is so tight that last vm is not able to schedule)
    vm_adjusted_amount = round(vm_amount / int(vm_memory[:-2])) - 1

    return vm_adjusted_amount, vm_memory


def wait_vmi_failover(vm, orig_node):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_15MIN, sleep=5, func=lambda: vm.vmi.node.name
    )
    LOGGER.info(f"Waiting for {vm.name} to be moved from node {orig_node.name}")
    try:
        for sample in samples:
            if sample and sample != orig_node.name:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"VM {vm.name} failed to deploy on new node")
        raise


def get_descheduler_evicted_vms(descheduler_pod):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN, sleep=5, func=descheduler_pod.log
    )
    sample = None
    LOGGER.info("Checking descheduler log to get migrated VM names")
    try:
        for sample in samples:
            if "Total number of pods evicted" in sample:
                LOGGER.info("Descheduler evicted VMs")
                return re.findall(r"-(vm-\d*-\d*-\d*)-", sample)
    except TimeoutExpiredError:
        LOGGER.error(sample)
        LOGGER.error("No VMs evicted by descheduler")
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
        sleep=5,
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
        sleep=5,
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
        vms (list): list of VM objects

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


@pytest.fixture(scope="module")
def skip_if_1tb_memory_or_more_node(workers_free_memory):
    """
    One of QE BM setups has worker with 5 TiB RAM memory while rest workers
    has 120 GiB RAM. Test should be skipped on this cluster, since all VMs will
    always land on 5 TiB RAM and descheduler will not do anything
    """
    for memory in workers_free_memory.values():
        if memory > 1024:
            pytest.skip("Cluster has node with more than 1 TiB RAM")


@pytest.fixture(scope="module")
def descheduler_ns(admin_client):
    yield from create_ns(
        admin_client=admin_client, name="openshift-kube-descheduler-operator"
    )


@pytest.fixture()
def installed_descheduler_og(descheduler_ns):
    with OperatorGroup(
        name="descheduler-operator-group",
        namespace=descheduler_ns.name,
        target_namespaces=[descheduler_ns.name],
    ):
        yield


@pytest.fixture()
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


@pytest.fixture()
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


@pytest.fixture()
def updated_descheduler_deployment(installed_descheduler):
    # Scale descheduler-operator to 0 is a W/A to force descheduler to use threasholds from config map
    Deployment(
        name="descheduler-operator", namespace=installed_descheduler.namespace
    ).scale_replicas(replica_count=0)


@pytest.fixture()
def updated_descheduler_policy(installed_descheduler, updated_descheduler_deployment):
    cm = ConfigMap(
        name=installed_descheduler.name, namespace=installed_descheduler.namespace
    )
    threshold_data = re.search(
        r"targetThresholds\D*(.*?)\D*?thresholdPriority",
        cm.instance["data"]["policy.yaml"],
        re.DOTALL,
    ).group(1)
    new_thresholds = (
        "60\n          memory: 60\n          pods: 60\n        thresholds:"
        "\n          cpu: 30\n          memory: 50\n          pods: 30"
    )
    ResourceEditor(
        patches={
            cm: {
                "data": {
                    "policy.yaml": re.sub(
                        threshold_data,
                        new_thresholds,
                        cm.instance["data"]["policy.yaml"],
                    )
                }
            }
        }
    ).update()


@pytest.fixture()
def updated_descheduler(admin_client, descheduler_ns, updated_descheduler_policy):
    get_pods(
        dyn_client=admin_client, namespace=descheduler_ns, label=DESCHEDULER_POD_LABEL
    )[
        0
    ].clean_up()  # apply cm update


@pytest.fixture(scope="module")
def workers_free_memory(schedulable_nodes, utility_pods):
    nodes_memory = {}
    cmd = "free -b | grep Mem | awk '{print $4,$6}'"
    for node in schedulable_nodes:
        pod_exec = ExecCommandOnPod(utility_pods=utility_pods, node=node)
        nodes_memory[node.name] = bitmath.Byte(
            sum([int(mem) for mem in pod_exec.exec(command=cmd).split()])
        ).to_GiB()
        LOGGER.info(
            f"Node {node.name} has {nodes_memory[node.name]} GiB of free memory"
        )
    return dict(sorted(nodes_memory.items(), key=lambda item: item[1]))


@pytest.fixture()
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


@pytest.mark.polarion("CNV-5922")
def test_descheduler(
    skip_if_1tb_memory_or_more_node,
    skip_when_one_node,
    updated_descheduler,
    deployed_vms,
    vms_started_process,
    node_to_drain,
    descheduler_pod,
    drain_node,
    schedulable_nodes,
):
    verify_running_process_after_failover(
        vms_list=deployed_vms, process_dict=vms_started_process
    )
    verify_vms_distribution_after_failover(vms=deployed_vms, nodes=schedulable_nodes)
