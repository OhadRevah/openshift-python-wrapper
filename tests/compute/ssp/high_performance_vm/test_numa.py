import re
from xml.etree import ElementTree

import pytest
from resources.pod import Pod
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
)


@pytest.fixture(scope="module")
def skip_if_cpumanager_disabled(schedulable_nodes):
    cpumanager_status = [
        True if node.instance.metadata.labels.cpumanager == "true" else False
        for node in schedulable_nodes
    ]
    if not any(cpumanager_status):
        pytest.skip(msg="Test should run on cluster with CPU Manager")


@pytest.fixture()
def vm_numa(namespace, unprivileged_client):
    name = "vm-numa"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        cpu_cores=8,
        cpu_sockets=2,
        body=fedora_vm_body(name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
        client=unprivileged_client,
        cpu_placement=True,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.fixture()
def numa_pod(vm_numa, default_client):
    return list(Pod.get(default_client, namespace=vm_numa.namespace))[0]


@pytest.fixture()
def vm_cpu_list(vm_numa, numa_pod):
    out = numa_pod.execute(
        command=["virsh", "vcpuinfo", f"{vm_numa.namespace}_{vm_numa.name}"]
    )
    return [x.split()[1] for x in out.split("\n") if re.search(r"^CPU:", out)]


@pytest.fixture()
def node_cpu_list(numa_pod):
    out = numa_pod.execute(command=["virsh", "capabilities"])
    tree = ElementTree.fromstring(out)
    return [
        x.get("cpus").split(",")
        for x in tree.findall("host")[0].findall("cache")[0].findall("bank")
    ]


@pytest.mark.polarion("CNV-4216")
def test_numa(
    skip_if_workers_vms,
    skip_if_cpumanager_disabled,
    numa_pod,
    node_cpu_list,
    vm_cpu_list,
):
    pod_limits = numa_pod.instance.spec.containers[0].resources.limits
    pod_requests = numa_pod.instance.spec.containers[0].resources.requests
    assert (
        pod_limits == pod_requests
    ), f"NUMA Pod has mismatch in resources lmits and requests. Limits {pod_limits}, requests {pod_requests}"
    assert (
        numa_pod.instance.status.qosClass == "Guaranteed"
    ), f"QOS Class in not Guaranteed. NUMA pod QOS Class {numa_pod.instance.status.qosClass}"
    assert (
        numa_pod.instance.spec.nodeSelector.cpumanager
    ), "NUMA Pod doesn't have cpumanager node selector"
    assert any(
        [all(x in cpu for x in vm_cpu_list) for cpu in node_cpu_list]
    ), f"Not all vCPUs are pinned in one numa node! VM vCPUS{vm_cpu_list}, NUMA node CPU lists"
