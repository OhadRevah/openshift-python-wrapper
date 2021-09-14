import pytest

from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


# flake8: noqa: PID


@pytest.mark.ci
def test_ci_container_disk_vm(
    namespace,
    unprivileged_client,
):
    name = "ci-container-disk-vm"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
    ) as vm:
        running_vm(vm=vm, check_ssh_connectivity=False)
