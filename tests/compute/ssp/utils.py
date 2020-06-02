import logging


LOGGER = logging.getLogger(__name__)


def check_vm_xml_smbios(vm, cm_values):
    """
    Verify SMBIOS on VM XML [sysinfo type=smbios][system] match kubevirt-config
    config map.
    """

    LOGGER.info("Verify VM XML - SMBIOS values.")
    smbios_vm = vm.vmi.xml_dict["domain"]["sysinfo"]["system"]["entry"]
    smbios_vm_dict = {entry["@name"]: entry["#text"] for entry in smbios_vm}
    assert smbios_vm, "VM XML missing SMBIOS values."
    results = {
        "Manufacturer": smbios_vm_dict["manufacturer"] == cm_values["Manufacturer"],
        "Product": smbios_vm_dict["product"] == cm_values["Product"],
        "Family": smbios_vm_dict["family"] == cm_values["Family"],
        "SKU": smbios_vm_dict["sku"] == cm_values["Sku"],
        "Version": smbios_vm_dict["version"] == cm_values["Version"],
    }
    LOGGER.info(f"Results: {results}")
    assert all(results.values())


def check_smbios_defaults(smbios_defaults, cm_values):
    LOGGER.info("Compare SMBIOS config map values to expected default values.")
    assert (
        cm_values == smbios_defaults
    ), f"Configmap values {cm_values} do not match default values {smbios_defaults}"


def validate_machine_type(expected_machine_type, vm):
    vm_machine_type = vm.instance.spec.template.spec.domain.machine.type
    vmi_machine_type = vm.vmi.instance.spec.domain.machine.type

    assert vm_machine_type == vmi_machine_type == expected_machine_type, (
        f"Created VM's machine type does not match the request. "
        f"Expected: {expected_machine_type} VM: {vm_machine_type}, VMI: {vmi_machine_type}"
    )
