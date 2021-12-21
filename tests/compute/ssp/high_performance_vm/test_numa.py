import re

import pytest
import xmltodict
from ocp_resources.sriov_network import SriovNetwork

from utilities.constants import SRIOV
from utilities.infra import BUG_STATUS_CLOSED, ExecCommandOnPod
from utilities.network import sriov_network_dict
from utilities.virt import VirtualMachineForTests, fedora_vm_body


pytestmark = [
    pytest.mark.usefixtures(
        "skip_if_workers_vms",
        "skip_if_no_cpumanager_workers",
        "skip_if_numa_not_configured_or_enabled",
    ),
    pytest.mark.bugzilla(
        2029343, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    ),
]


@pytest.fixture(scope="module")
def skip_if_numa_not_configured_or_enabled(schedulable_nodes, utility_pods):
    cat_cmd = "cat /etc/kubernetes/kubelet.conf"
    single_numa_node_cmd = f"{cat_cmd} | grep -i single-numa-node"
    topology_manager_cmd = f"{cat_cmd} | grep -w TopologyManager"
    for cmd in (single_numa_node_cmd, topology_manager_cmd):
        if not check_numa_config_on_node(
            cmd=cmd, schedulable_nodes=schedulable_nodes, utility_pods=utility_pods
        ):
            pytest.skip(msg=f"Test should run on nodes with {cmd.split()[-1]}")


def check_numa_config_on_node(cmd, schedulable_nodes, utility_pods):
    for node in schedulable_nodes:
        pod_exec = ExecCommandOnPod(utility_pods=utility_pods, node=node)
        out = pod_exec.exec(command=cmd, ignore_rc=True)
        if not out:
            return False
    return True


@pytest.fixture(scope="module")
def skip_if_no_cpumanager_workers(schedulable_nodes):
    cpumanager_status = [
        True if node.labels.cpumanager == "true" else False
        for node in schedulable_nodes
    ]
    if not any(cpumanager_status):
        pytest.skip(msg="Test should run on cluster with CPU Manager")


@pytest.fixture(scope="module")
def sriov_net(sriov_node_policy, namespace):
    with SriovNetwork(
        name="numa-sriov-test-net",
        namespace=sriov_node_policy.namespace,
        resource_name=sriov_node_policy.resource_name,
        network_namespace=namespace.name,
    ) as net:
        yield net


@pytest.fixture()
def vm_numa(namespace, unprivileged_client):
    name = "vm-numa"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        cpu_cores=8,
        cpu_sockets=2,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        cpu_placement=True,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.fixture()
def vm_numa_sriov(namespace, unprivileged_client, sriov_net):
    name = "vm-numa-sriov"
    networks = sriov_network_dict(namespace=namespace, network=sriov_net)
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        cpu_cores=8,
        cpu_sockets=2,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        cpu_placement=True,
        networks=networks,
        interfaces=networks.keys(),
        interfaces_types={name: SRIOV for name in networks.keys()},
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


def get_vm_cpu_list(vm):
    vcpuinfo = vm.vmi.virt_launcher_pod.execute(
        command=["virsh", "vcpuinfo", f"{vm.namespace}_{vm.name}"]
    )

    return [cpu.split()[1] for cpu in vcpuinfo.split("\n") if re.search(r"^CPU:", cpu)]


def get_numa_node_cpu_dict(vm):
    """
    Get NUMA nodes CPU lists.
    Return dict:
        {'<numa_node_id>': [cpu_list]}
    """
    out = vm.vmi.virt_launcher_pod.execute(command=["virsh", "capabilities"])
    numa = xmltodict.parse(out)["capabilities"]["host"]["cache"]["bank"]

    return {elem["@id"]: elem["@cpus"].split(",") for elem in numa}


def get_numa_cpu_allocation(vm_cpus, numa_nodes):
    """
    Find NUMA node # where VM CPUs are allocated.
    """

    def _parse_ranges_to_list(ranges):
        cpus = []
        for elem in ranges:
            if "-" in elem:
                start, end = elem.split("-")
                cpus.extend([str(x) for x in range(int(start), int(end) + 1)])
            else:
                cpus.append(elem)
        return cpus

    for node in numa_nodes.keys():
        if all(cpu in _parse_ranges_to_list(numa_nodes[node]) for cpu in vm_cpus):
            return node


def get_sriov_pci_address(vm):
    """
    Get PCI address of SRIOV device in virsh.
    Return str:
        'a:b:c.d' (for e.g. '0000:3b:0a.2')
    """
    addr = vm.vmi.xml_dict["domain"]["devices"]["hostdev"]["source"]["address"]

    return f'{addr["@domain"][2:]}:{addr["@bus"][2:]}:{addr["@slot"][2:]}.{addr["@function"][2:]}'


def get_numa_sriov_allocation(vm, utility_pods):
    """
    Find NUMA node # where SR-IOV device is allocated.
    """
    sriov_addr = get_sriov_pci_address(vm=vm)
    out = ExecCommandOnPod(utility_pods=utility_pods, node=vm.vmi.node).exec(
        command=f"cat /sys/bus/pci/devices/{sriov_addr}/numa_node"
    )

    return out.strip()


@pytest.mark.polarion("CNV-4216")
def test_numa(vm_numa):
    numa_pod = vm_numa.vmi.virt_launcher_pod.instance
    pod_limits = numa_pod.spec.containers[0].resources.limits
    pod_requests = numa_pod.spec.containers[0].resources.requests
    vm_cpu_list = get_vm_cpu_list(vm=vm_numa)
    numa_node_dict = get_numa_node_cpu_dict(vm=vm_numa)

    assert (
        pod_limits == pod_requests
    ), f"NUMA Pod has mismatch in resources lmits and requests. Limits {pod_limits}, requests {pod_requests}"
    assert (
        numa_pod.status.qosClass == "Guaranteed"
    ), f"QOS Class in not Guaranteed. NUMA pod QOS Class {numa_pod.status.qosClass}"
    assert (
        numa_pod.spec.nodeSelector.cpumanager
    ), "NUMA Pod doesn't have cpumanager node selector"
    assert get_numa_cpu_allocation(
        vm_cpus=vm_cpu_list, numa_nodes=numa_node_dict
    ), f"Not all vCPUs are pinned in one numa node! VM vCPUS {vm_cpu_list}, NUMA node CPU lists {numa_node_dict}"


@pytest.mark.polarion("CNV-4309")
def test_numa_with_sriov(
    skip_when_no_sriov,
    vm_numa_sriov,
    utility_pods,
):
    cpu_alloc = get_numa_cpu_allocation(
        vm_cpus=get_vm_cpu_list(vm=vm_numa_sriov),
        numa_nodes=get_numa_node_cpu_dict(vm=vm_numa_sriov),
    )
    sriov_alloc = get_numa_sriov_allocation(vm=vm_numa_sriov, utility_pods=utility_pods)

    assert (
        cpu_alloc == sriov_alloc
    ), f"SR-IOV and CPUs are on different NUMA nodes! CPUs allocated to node {cpu_alloc}, SR-IOV to node {sriov_alloc}"
