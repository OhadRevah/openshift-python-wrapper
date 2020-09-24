"""
EFI secureBoot VM
"""

import logging
import os

import pytest
from openshift.dynamic.exceptions import UnprocessibleEntityError
from pytest_testconfig import config as py_config
from resources.resource import ResourceEditor
from utilities import console
from utilities.infra import Images
from utilities.virt import (
    VirtualMachineForTests,
    vm_console_run_commands,
    wait_for_console,
    wait_for_vm_interfaces,
)


LOGGER = logging.getLogger(__name__)
VM_CPU = 2
VM_MEMORY = 1
RHEL_EFI_IMG = os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL8_2_EFI_IMG)


@pytest.fixture(scope="class")
def efi_secureboot_vm(request, namespace, unprivileged_client, data_volume_scope_class):
    """ Create VM with EFI secureBoot set as True """
    with VirtualMachineForTests(
        name="rhel-efi-secureboot-default",
        namespace=namespace.name,
        client=unprivileged_client,
        data_volume=data_volume_scope_class,
        cpu_cores=VM_CPU,
        memory=f"{VM_MEMORY}Gi",
        smm_enabled=True,
        efi_params=request.param.get("efi_params"),
    ) as vm:
        start_and_wait_for_vm_console(vm=vm, console_impl=console.RHEL)
        yield vm


def start_and_wait_for_vm_console(vm, console_impl):
    vm.start(wait=True)
    vm.vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vm.vmi)
    wait_for_console(vm=vm, console_impl=console_impl)


def validate_efi_vm_and_vm_xml(vm):
    """
    Verify EFI directory structure exists and VM XML is secureBoot enabled.
    """
    vm_console_run_commands(
        console_impl=console.RHEL,
        vm=vm,
        commands=["ls -ld /sys/firmware/efi"],
    )

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
    vm.stop(wait=True)
    start_and_wait_for_vm_console(vm=vm, console_impl=console.RHEL)


@pytest.mark.parametrize(
    "data_volume_scope_class, efi_secureboot_vm",
    [
        pytest.param(
            {
                "dv_name": "dv-rhel-efi-secureboot-withdv",
                "image": RHEL_EFI_IMG,
                "storage_class": py_config["default_storage_class"],
            },
            {"efi_params": {"secureBoot": True}},
        ),
    ],
    indirect=True,
)
class TestEFISecureBoot:
    """
    Test EFI secureBoot VM with RHEL Images in DV.
    """

    @pytest.mark.run(before="test_efi_secureboot_is_default")
    @pytest.mark.polarion("CNV-1791")
    def test_secureboot_efi(self, data_volume_scope_class, efi_secureboot_vm):
        """
        Test VM boots with efi secureboot and check vm_xml values
        """
        validate_efi_vm_and_vm_xml(vm=efi_secureboot_vm)

    @pytest.mark.run(before="test_efi_secureboot_is_default")
    @pytest.mark.polarion("CNV-1789")
    def test_efi_secureboot_vm_cpu_and_memory(
        self, data_volume_scope_class, efi_secureboot_vm
    ):
        """
        Test EFI secureBoot VM cpu and memory values specified in spec match
        """
        vm_console_run_commands(
            console_impl=console.RHEL,
            vm=efi_secureboot_vm,
            commands=[
                f"sudo dmidecode -t 17 | awk '/Size/{{print $2,$3}}' | grep \"{VM_MEMORY} GB\"",
                f"nproc | grep {VM_CPU}",
            ],
        )

    @pytest.mark.run(after="test_secureboot_efi")
    @pytest.mark.polarion("CNV-1790")
    def test_efi_secureboot_is_default(
        self, data_volume_scope_class, efi_secureboot_vm
    ):
        """
        Test VM with EFI is set as secureBoot by default.
        """
        _update_vm_efi_spec(vm=efi_secureboot_vm)
        validate_efi_vm_and_vm_xml(vm=efi_secureboot_vm)


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
