import pytest

from utilities.infra import cluster_resource
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


@pytest.mark.smoke
@pytest.mark.polarion("CNV-5501")
def test_container_disk_vm(
    namespace,
    unprivileged_client,
):
    name = "container-disk-vm"
    with cluster_resource(VirtualMachineForTests)(
        namespace=namespace.name,
        name=name,
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
    ) as vm:
        running_vm(vm=vm)
