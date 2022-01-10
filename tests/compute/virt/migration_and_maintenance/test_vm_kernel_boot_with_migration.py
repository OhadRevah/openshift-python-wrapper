import logging

import pytest
from ocp_resources.resource import ResourceEditor

from utilities.console import Console
from utilities.constants import TIMEOUT_3MIN
from utilities.infra import BUG_STATUS_CLOSED
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    migrate_vm_and_verify,
    running_vm,
)


LOGGER = logging.getLogger(__name__)

KERNEL_ARGUMENT = "awesome_argument"


def add_kernel_boot_block(vm):
    ResourceEditor(
        {
            vm: {
                "spec": {
                    "template": {
                        "spec": {
                            "domain": {
                                "firmware": {
                                    "kernelBoot": {
                                        "container": {
                                            "image": "quay.io/kubevirt/alpine-ext-kernel-boot-demo",
                                            "initrdPath": "/boot/initramfs-virt",
                                            "kernelPath": "/boot/vmlinuz-virt",
                                        },
                                        "kernelArgs": f"console=ttyS0 {KERNEL_ARGUMENT}",
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    ).update()


@pytest.fixture()
def vm_with_kernel_boot(
    unprivileged_client,
    namespace,
):
    name = "kernel-boot-vm"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
    ) as vm:
        add_kernel_boot_block(vm=vm)
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)
        yield vm


@pytest.fixture()
def kernel_boot_console(vm_with_kernel_boot):
    with Console(vm=vm_with_kernel_boot, prompt="#") as vmc:
        yield vmc


@pytest.fixture()
def migrated_vm_with_kernel_boot(vm_with_kernel_boot):
    migrate_vm_and_verify(
        vm=vm_with_kernel_boot,
        timeout=TIMEOUT_3MIN,
        wait_for_interfaces=False,
        check_ssh_connectivity=False,
    )


@pytest.mark.bugzilla(
    2039976, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)
@pytest.mark.polarion("CNV-7749")
def test_vm_kernel_boot_after_migration(
    skip_when_one_node,
    vm_with_kernel_boot,
    migrated_vm_with_kernel_boot,
    kernel_boot_console,
):
    kernel_boot_console.sendline("cat /proc/cmdline")
    kernel_boot_console.expect(KERNEL_ARGUMENT)
