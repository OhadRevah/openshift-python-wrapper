import logging
from bisect import bisect
from collections import Counter

from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler

from tests.compute.ssp.descheduler.constants import (
    DESCHEDULING_INTERVAL_120SEC,
    RUNNING_PROCESS_NAME_IN_VM,
)
from tests.compute.utils import fetch_processid_from_linux_vm
from utilities.constants import TIMEOUT_1MIN, TIMEOUT_5SEC, TIMEOUT_10MIN, TIMEOUT_15MIN
from utilities.virt import VirtualMachineForTests, fedora_vm_body


LOGGER = logging.getLogger(__name__)


class UnexpectedBehaviorError(Exception):
    def __init__(self, error_msg):
        self.error_msg = error_msg

    def __str__(self):
        return f"Unexpected behavior: {self.error_msg}"


class VirtualMachineForDeschedulerTest(VirtualMachineForTests):
    def __init__(
        self,
        name,
        namespace,
        memory_requests,
        client,
        cpu_model,
        cpu_requests=None,
        descheduler_eviction=True,
    ):
        super().__init__(
            name=name,
            namespace=namespace,
            client=client,
            memory_requests=memory_requests,
            eviction=True,
            cpu_model=cpu_model,
            cpu_requests=cpu_requests,
        )
        self.descheduler_eviction = descheduler_eviction

    def to_dict(self):
        self.body = fedora_vm_body(name=self.name)
        res = super().to_dict()
        metadata = res["spec"]["template"]["metadata"]
        metadata.setdefault("annotations", {})
        if self.descheduler_eviction:
            metadata["annotations"]["descheduler.alpha.kubernetes.io/evict"] = "true"

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

    # Allow the descheduler to cycle multiple times before returning.
    # The value can be affected by high pod counts or load within
    # the cluster which increases the descheduler runtime.
    descheduling_failover_timeout = DESCHEDULING_INTERVAL_120SEC * 3

    sample = None
    samples = TimeoutSampler(
        wait_timeout=descheduling_failover_timeout,
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


def verify_vms_consistent_virt_launcher_pods(running_vms):
    """Verify VMs virt launcher pods are not replaced (sampled every one minute).

    Using VMs virt launcher pods to verify that VMs are not migrated nor restarted.

    Args:
        running_vms (list): list of VMs
    """

    def _vms_launcher_pod_names():
        return {
            vm.name: vm.vmi.virt_launcher_pod.name
            for vm in running_vms
            if vm.vmi.virt_launcher_pod.status
            == vm.vmi.virt_launcher_pod.Status.RUNNING
        }

    orig_virt_launcher_pod_names = _vms_launcher_pod_names()
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=TIMEOUT_1MIN,
        func=_vms_launcher_pod_names,
    )
    try:
        for sample in samples:
            if any(
                [
                    pod_name != orig_virt_launcher_pod_names[vm_name]
                    for vm_name, pod_name in sample.items()
                ]
            ):
                raise UnexpectedBehaviorError(
                    error_msg=f"Some VMs were migrated: {sample} from {orig_virt_launcher_pod_names}"
                )

    except TimeoutExpiredError:
        LOGGER.info("No VMs were migrated.")


def has_kubevirt_owner(resource):
    return any(
        [
            owner_reference.apiVersion.startswith(f"{resource.ApiGroup.KUBEVIRT_IO}/")
            for owner_reference in resource.instance.metadata.get("ownerReferences", [])
        ]
    )
