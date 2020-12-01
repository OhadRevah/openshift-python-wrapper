import pytest

from utilities.console import Fedora
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_console,
)


@pytest.mark.smoke
@pytest.mark.polarion("CNV-5501")
def test_container_disk_vm(
    namespace,
    unprivileged_client,
):
    name = "container-disk-vm"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
    ) as vm:
        vm.start(wait=True)
        wait_for_console(vm=vm, console_impl=Fedora)
