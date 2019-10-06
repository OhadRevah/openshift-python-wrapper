"""
VM with CPU features
"""
import pytest
from pytest_testconfig import config as py_config
from resources.configmap import ConfigMap
from resources.node import Node
from resources.utils import TimeoutExpiredError
from utilities import console
from utilities.virt import VirtualMachineForTests, wait_for_vm_interfaces


@pytest.fixture(
    params=[
        pytest.param(
            [{"features": [{"name": "pcid"}]}, "no-policy"],
            marks=(pytest.mark.polarion("CNV-1830")),
        ),
        pytest.param(
            [{"features": [{"name": "pcid", "policy": "force"}]}, "policy-force"],
            marks=(pytest.mark.polarion("CNV-1836")),
        ),
    ],
    ids=["Feature: name: pcid", "Feature: name: pcid , policy:force"],
)
def cpu_features_vm_positive(request, default_client, cpu_features_namespace):
    with VirtualMachineForTests(
        name=f"vm-cpu-features-positive-{request.param[1]}",
        namespace=cpu_features_namespace.name,
        cpu_flags=request.param[0],
    ) as vm:
        vm.start(wait=True, timeout=240)
        vm.vmi.wait_until_running()
        wait_for_vm_interfaces(vm.vmi)
        yield vm


@pytest.fixture(
    params=[
        pytest.param(
            [{"features": [{"name": "nomatch"}]}, "nomatch"],
            marks=(pytest.mark.polarion("CNV-1833")),
        ),
        pytest.param(
            [{"features": [{"name": "pcid", "policy": "forbid"}]}, "policy-forbid"],
            marks=(pytest.mark.polarion("CNV-1835")),
        ),
    ],
    ids=["Feature: name: nomatch", "Feature: name: pcid , policy:forbid "],
)
def cpu_features_vm_negative(request, default_client, cpu_features_namespace):
    with VirtualMachineForTests(
        name=f"vm-cpu-features-negative-{request.param[1]}",
        namespace=cpu_features_namespace.name,
        cpu_flags=request.param[0],
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture()
def cpu_features_vm_require_pcid(cpu_features_namespace):
    with VirtualMachineForTests(
        name=f"vm-cpu-features-require",
        namespace=cpu_features_namespace.name,
        cpu_flags={"features": [{"name": "pcid", "policy": "require"}]},
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture()
def config_map_with_cpu_discovery(default_client):
    config_map_namespace = py_config["hco_namespace"]
    cpu_node_discovery = "CPUNodeDiscovery"

    kubevirt_config_map = ConfigMap(
        name="kubevirt-config", namespace=config_map_namespace
    )
    original_feature_gates = kubevirt_config_map.instance["data"]["feature-gates"]
    feature_gates = original_feature_gates.split(",")

    if cpu_node_discovery not in feature_gates:
        try:
            feature_gates.append(cpu_node_discovery)
            new_config_map_dict = kubevirt_config_map.instance.to_dict()
            new_config_map_dict["data"]["feature-gates"] = ",".join(feature_gates)
            kubevirt_config_map.update(new_config_map_dict)
            yield
        finally:
            to_restore_config_map_dict = kubevirt_config_map.instance.to_dict()
            to_restore_config_map_dict["data"]["feature-gates"] = original_feature_gates
            kubevirt_config_map.update(to_restore_config_map_dict)
    else:
        yield


@pytest.fixture()
def nodes_with_no_pciid_label(default_client):
    nodes_with_cpu_feature = Node.get(
        default_client,
        label_selector=f"feature.node.kubernetes.io/cpu-feature-pcid=true",
    )

    nodes_to_restore = []
    try:
        for node in nodes_with_cpu_feature:
            node_dict = node.instance.to_dict()
            node_dict["metadata"]["labels"][
                "feature.node.kubernetes.io/cpu-feature-pcid"
            ] = "false"
            node.update(node_dict)

            nodes_to_restore.append(node.name)
        yield
    finally:
        for node_name in nodes_to_restore:
            node = Node(name=node_name)
            to_restore = node.instance.to_dict()
            to_restore["metadata"]["labels"][
                "feature.node.kubernetes.io/cpu-feature-pcid"
            ] = "true"
            node.update(to_restore)


def test_vm_with_cpu_feature_positive(cpu_features_vm_positive):
    """
    Test VM with cpu flag, test the VM started and enter the console
    """
    assert cpu_features_vm_positive.cpu_flags["features"][0]["name"] == (
        cpu_features_vm_positive.instance["spec"]["template"]["spec"]["domain"]["cpu"][
            "features"
        ][0]["name"]
    )
    with console.Fedora(vm=cpu_features_vm_positive) as vm_console:
        vm_console.sendline("cat /etc/redhat-release | wc -l\n")
        vm_console.expect("1", timeout=20)


def test_vm_with_cpu_feature_negative(cpu_features_vm_negative):
    """
    Negative test:
    Test VM with wrong/unsupported cpu feature policy,
    VM should not run in this case.
    """
    with pytest.raises(TimeoutExpiredError):
        cpu_features_vm_negative.vmi.wait_until_running(timeout=60)


@pytest.mark.polarion("CNV-1834")
def test_vm_with_cpu_feature_required_not_schedulable(
    nodes_with_no_pciid_label,
    config_map_with_cpu_discovery,
    cpu_features_vm_require_pcid,
):
    """
    Negative test:
    Test VM with required cpu type, no node available.
    VM should not be able to get scheduled in this case.
    """
    with pytest.raises(TimeoutExpiredError):
        cpu_features_vm_require_pcid.vmi.wait_until_running(timeout=120)
