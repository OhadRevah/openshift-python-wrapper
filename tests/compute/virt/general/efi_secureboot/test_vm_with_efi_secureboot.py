"""
EFI secureBoot VM
"""

import logging
import os
import shlex

import pytest
from ocp_resources.resource import ResourceEditor
from ocp_resources.template import Template
from openshift.dynamic.exceptions import UnprocessibleEntityError
from pytest_testconfig import config as py_config

from tests.compute.utils import vm_started
from utilities import console
from utilities.infra import BUG_STATUS_CLOSED, Images
from utilities.virt import (
    VirtualMachineForTests,
    VirtualMachineForTestsFromTemplate,
    migrate_and_verify,
    vm_console_run_commands,
    wait_for_console,
    wait_for_windows_vm,
)


LOGGER = logging.getLogger(__name__)
VM_CPU = 2
VM_MEMORY = 1
RHEL_EFI_IMG = os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL8_2_EFI_IMG)
WIN_EFI_IMG = os.path.join(Images.Windows.DIR, Images.Windows.WIM10_EFI_IMG)


@pytest.fixture(scope="class")
def rhel_efi_secureboot_vm(namespace, unprivileged_client, data_volume_scope_class):
    """ Create VM with EFI secureBoot set as True """
    with VirtualMachineForTests(
        name="rhel-efi-secureboot-default",
        namespace=namespace.name,
        client=unprivileged_client,
        data_volume=data_volume_scope_class,
        cpu_cores=VM_CPU,
        memory_requests=f"{VM_MEMORY}Gi",
        smm_enabled=True,
        efi_params={"secureBoot": True},
    ) as vm:
        vm_started(vm=vm)
        wait_for_console(vm=vm, console_impl=console.RHEL)
        yield vm


@pytest.fixture(scope="class")
def windows_efi_secureboot_vm(
    namespace,
    unprivileged_client,
    golden_image_data_volume_scope_class,
    nodes_common_cpu_model,
):
    """ Create VM with EFI secureBoot set as True """
    with VirtualMachineForTestsFromTemplate(
        name="windows-efi-secureboot",
        namespace=namespace.name,
        client=unprivileged_client,
        labels=Template.generate_template_labels(
            **py_config["system_windows_os_matrix"][0]["win-10"]["template_labels"]
        ),
        data_volume=golden_image_data_volume_scope_class,
        cpu_cores=VM_CPU,
        smm_enabled=True,
        efi_params={"secureBoot": True},
        cpu_model=nodes_common_cpu_model,
    ) as vm:
        vm_started(vm=vm, wait_for_interfaces=False)
        wait_for_windows_vm(
            vm=vm, version=vm.template_labels[0].split("win")[1], timeout=1800
        )
        yield vm


def validate_vm_xml_efi(vm):
    LOGGER.info("Verify VM XML - EFI secureBoot values.")
    os = vm.vmi.xml_dict["domain"]["os"]
    efi_path = "/usr/share/OVMF/OVMF_CODE.secboot.fd"
    efi_vars_path = "/usr/share/OVMF/OVMF_VARS.secboot.fd"
    vmi_xml_efi_path = os["loader"]["#text"]
    vmi_xml_efi_vars_path = os["nvram"]["@template"]
    vmi_xml_os_secure = os["loader"]["@secure"]
    assert (
        vmi_xml_efi_path == efi_path
    ), f"EFIPath value {vmi_xml_efi_path} does not match expected {efi_path} value"
    assert (
        vmi_xml_os_secure == "yes"
    ), f"EFI secure value {vmi_xml_os_secure} does not seem to be set as YES"
    assert (
        vmi_xml_efi_vars_path == efi_vars_path
    ), f"EFIVarsPath value {vmi_xml_efi_vars_path} does not match expected {efi_vars_path} value"


def validate_linux_efi(vm):
    """
    Verify guest OS is using EFI.
    """
    vm_console_run_commands(
        console_impl=console.RHEL, vm=vm, commands=["ls -ld /sys/firmware/efi"]
    )


def validate_windows_efi(ssh_exec):
    """
    Verify guest OS is using EFI.
    """
    _, out, _ = ssh_exec.run_command(command=shlex.split("bcdedit | findstr EFI"))
    assert (
        "\\EFI\\Microsoft\\Boot\\bootmgfw.efi" in out
    ), f"EFI boot not fount in path. bcdedit output:\n{out}"


def _update_vm_efi_spec(vm):
    ResourceEditor(
        {
            vm: {
                "spec": {
                    "template": {
                        "spec": {"domain": {"firmware": {"bootloader": {"efi": {}}}}}
                    }
                }
            }
        }
    ).update()
    vm.restart(wait=True)
    wait_for_console(vm=vm, console_impl=console.RHEL)


@pytest.mark.parametrize(
    "data_volume_scope_class",
    [
        pytest.param(
            {
                "dv_name": "dv-rhel-efi-secureboot-withdv",
                "image": RHEL_EFI_IMG,
                "storage_class": py_config["default_storage_class"],
                "dv_size": Images.Rhel.DEFAULT_DV_SIZE,
            }
        ),
    ],
    indirect=True,
)
class TestEFISecureBootRHEL:
    """
    Test EFI secureBoot VM with RHEL Images in DV.
    """

    @pytest.mark.run(before="test_efi_secureboot_is_default")
    @pytest.mark.polarion("CNV-1791")
    def test_secureboot_efi(self, data_volume_scope_class, rhel_efi_secureboot_vm):
        """
        Test VM boots with efi secureboot and check vm_xml values
        """
        validate_vm_xml_efi(vm=rhel_efi_secureboot_vm)
        validate_linux_efi(vm=rhel_efi_secureboot_vm)

    @pytest.mark.run(before="test_efi_secureboot_is_default")
    @pytest.mark.polarion("CNV-1789")
    def test_efi_secureboot_vm_cpu_and_memory(
        self, data_volume_scope_class, rhel_efi_secureboot_vm
    ):
        """
        Test EFI secureBoot VM cpu and memory values specified in spec match
        """
        vm_console_run_commands(
            console_impl=console.RHEL,
            vm=rhel_efi_secureboot_vm,
            commands=[
                f"sudo dmidecode -t 17 | awk '/Size/{{print $2,$3}}' | grep \"{VM_MEMORY} GB\"",
                f"nproc | grep {VM_CPU}",
            ],
        )

    @pytest.mark.run(after="test_secureboot_efi")
    @pytest.mark.polarion("CNV-1790")
    def test_efi_secureboot_is_default(
        self, data_volume_scope_class, rhel_efi_secureboot_vm
    ):
        """
        Test VM with EFI is set as secureBoot by default.
        """
        _update_vm_efi_spec(vm=rhel_efi_secureboot_vm)
        validate_vm_xml_efi(vm=rhel_efi_secureboot_vm)
        validate_linux_efi(vm=rhel_efi_secureboot_vm)


@pytest.mark.polarion("CNV-4465")
def test_efi_secureboot_with_smm_disabled(namespace, unprivileged_client):
    """ Test that EFI secureBoot VM with SMM disabled, does not get created"""
    with pytest.raises(UnprocessibleEntityError):
        with VirtualMachineForTests(
            name="efi-secureboot-smm-disabled-vm",
            namespace=namespace.name,
            image="kubevirt/microlivecd-container-disk-demo",
            client=unprivileged_client,
            smm_enabled=False,
            efi_params={"secureBoot": True},
        ):
            pytest.fail(
                "VM created with EFI SecureBoot enabled. SecureBoot requires SMM, which is currently disabled"
            )


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class",
    [
        pytest.param(
            {
                "dv_name": "dv-windows-efi-secureboot",
                "image": WIN_EFI_IMG,
                "storage_class": py_config["default_storage_class"],
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            },
        ),
    ],
    indirect=True,
)
class TestEFISecureBootWindows:
    """
    Test EFI secureBoot VM with Windows Images in DV.
    """

    @pytest.mark.polarion("CNV-5464")
    def test_secureboot_efi(
        self,
        windows_efi_secureboot_vm,
    ):
        """
        Test VM boots with efi secureboot and check vm_xml values
        """
        validate_vm_xml_efi(vm=windows_efi_secureboot_vm)
        validate_windows_efi(ssh_exec=windows_efi_secureboot_vm.ssh_exec)

    @pytest.mark.bugzilla(
        1911118, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
    )
    @pytest.mark.polarion("CNV-5465")
    def test_migrate_vm_windows(
        self,
        skip_access_mode_rwo_scope_class,
        windows_efi_secureboot_vm,
    ):
        """Test EFI Windows VM is migrated."""

        migrate_and_verify(vm=windows_efi_secureboot_vm, check_ssh_connectivity=True)
        validate_vm_xml_efi(vm=windows_efi_secureboot_vm)
        validate_windows_efi(ssh_exec=windows_efi_secureboot_vm.ssh_exec)
