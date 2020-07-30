"""
Test VM with RNG
"""

import pytest
from utilities import console
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


@pytest.fixture()
def rng_vm(unprivileged_client, namespace):
    name = "vmi-with-rng"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        wait_for_vm_interfaces(vmi=vm.vmi)
        yield vm


@pytest.mark.polarion("CNV-791")
def test_vm_with_rng(rng_vm):
    """
    Test VM with RNG
     - check random device should be present
     - create random data with each device
    """
    with console.Fedora(vm=rng_vm) as vm_console:
        vm_console.sendline("cat /sys/devices/virtual/misc/hw_random/rng_current")
        vm_console.expect("virtio_rng.0", timeout=20)
        for device in ["random", "hwrng"]:
            vm_console.sendline(
                f"sudo dd count=10 bs=1024 if=/dev/{device} of=/tmp/{device}.txt"
            )
            vm_console.sendline(f"ls /tmp/{device}.txt | wc -l")
            vm_console.expect("1", timeout=20)
