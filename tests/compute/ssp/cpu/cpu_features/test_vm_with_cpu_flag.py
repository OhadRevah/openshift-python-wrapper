"""
VM with CPU flag
"""
import pytest
from resources.node import Node
from resources.utils import TimeoutExpiredError
from utilities import console
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


@pytest.fixture()
def cpu_module(admin_client):
    """
    Get the cpu module supported on nodes (query node with feature.node.kubernetes.io/cpu-model-{module})
    Skip the test if no node has the following CPU module:
    "Haswell", "Haswell-noTSX", "Westmere", "IvyBridge", "SandyBridge"
    """
    cpu_module = ["Haswell", "Haswell-noTSX", "Westmere", "IvyBridge", "SandyBridge"]
    for cpu in cpu_module:
        node_with_cpu = Node.get(
            admin_client,
            label_selector=f"feature.node.kubernetes.io/cpu-model-{cpu}=true",
        )
        if len(list(node.name for node in node_with_cpu)) > 1:
            return cpu
    pytest.skip(msg=f"Did not find node with CPU modules: {cpu_module}")


@pytest.fixture()
def cpu_flag_vm_positive(cpu_module, namespace, unprivileged_client):
    name = "vm-cpu-flags-positive"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        cpu_flags={"model": cpu_module},
        body=fedora_vm_body(name=name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True, timeout=240)
        vm.vmi.wait_until_running()
        wait_for_vm_interfaces(vmi=vm.vmi)
        yield vm


@pytest.fixture(
    params=[
        pytest.param(
            [{"model": "Bad-Skylake-Server"}, "bad-skylake-server"],
            marks=(pytest.mark.polarion("CNV-1272")),
        ),
        pytest.param(
            [{"model": "commodore64"}, "commodore64"],
            marks=(pytest.mark.polarion("CNV-1273")),
        ),
    ],
    ids=["CPU-flag: Bad-Skylake-Server", "CPU-flag: commodore64"],
)
def cpu_flag_vm_negative(request, unprivileged_client, namespace):
    name = f"vm-cpu-flags-negative-{request.param[1]}"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        cpu_flags=request.param[0],
        body=fedora_vm_body(name=name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
        client=unprivileged_client,
    ) as vm:
        vm.start()
        yield vm


def test_vm_with_cpu_flag_negative(cpu_flag_vm_negative):
    """
    Negative test:
    Test VM with wrong cpu model,
    VM should not run in this case since cpu model not exists on host
    """
    with pytest.raises(TimeoutExpiredError):
        cpu_flag_vm_negative.vmi.wait_until_running(timeout=60)


@pytest.mark.polarion("CNV-1269")
def test_vm_with_cpu_flag_positive_case(cpu_flag_vm_positive):
    """
    Test VM with cpu flag, test the VM started and enter the console
    """
    assert cpu_flag_vm_positive.cpu_flags["model"] == (
        cpu_flag_vm_positive.instance["spec"]["template"]["spec"]["domain"]["cpu"][
            "model"
        ]
    )
    with console.Fedora(vm=cpu_flag_vm_positive) as vm_console:
        vm_console.sendline("cat /etc/redhat-release | wc -l\n")
        vm_console.expect("1", timeout=20)
