# -*- coding: utf-8 -*-

"""
VM with sidecar
"""
import pytest

from tests.fixtures import (
    create_vms_from_template,
    wait_until_vmis_running,
    wait_for_vmis_interfaces_report,
    start_vms,
)
from tests.virt.vm_with_sidecar import config
from utilities import console

CHECK_DMIDECODE_PACKAGE = "sudo dmidecode -s baseboard-manufacturer | grep 'Radical Edward' | wc -l\n"


class TestVMWithSidecar(object):
    """
    Test VM with sidecar
    """
    vms = config.VMS
    namespace = config.VIRT_NS
    template = config.VM_YAML_FEDORA
    template_kwargs = config.VM_FEDORA_ATTRS

    @pytest.mark.usefixtures(
        create_vms_from_template.__name__,
        start_vms.__name__,
        wait_until_vmis_running.__name__,
        wait_for_vmis_interfaces_report.__name__,
    )
    def test_vm_with_sidecar_hook(self):
        """
        Test VM with sidecar hook, Install dmidecode with annotation
        smbios.vm.kubevirt.io/baseBoardManufacturer: "Radical Edward"
        And check that package includes manufacturer: "Radical Edward"
        """
        with console.Fedora(vm=config.VM_NAME, namespace=config.VIRT_NS) as vm_console:
            vm_console.sendline(CHECK_DMIDECODE_PACKAGE)
            vm_console.expect("1", timeout=20)
