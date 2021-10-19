import pytest

from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


# flake8: noqa: PID
pytestmark = pytest.mark.ci


def test_ci_container_disk_vm(admin_client, namespace):
    name = "ci-container-disk-vm"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
    ) as vm:
        running_vm(vm=vm, check_ssh_connectivity=False)


def test_schedulable_nodes(schedulable_nodes):
    return


def test_masters(masters):
    return


def test_utility_daemonset(utility_daemonset):
    return


def test_utility_pods(utility_pods):
    return
