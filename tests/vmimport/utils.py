from resources.virtual_machine_import import VirtualMachineImport


class OvirtMappings:
    def __init__(
        self, disk_mappings=None, network_mappings=None, storage_mappings=None
    ):
        self.disk_mappings = disk_mappings
        self.network_mappings = network_mappings
        self.storage_mappings = storage_mappings


class ResourceMappingItem:
    def __init__(
        self,
        target_name,
        target_namespace=None,
        target_type=None,
        source_name=None,
        source_id=None,
    ):
        self.target_name = target_name
        self.target_namespace = target_namespace
        self.source_name = source_name
        self.source_id = source_id
        self.target_type = target_type


POD_MAPPING = ResourceMappingItem(
    target_name="pod", target_type="pod", source_name="ovirtmgmt/ovirtmgmt"
)


def network_mappings(items):
    ovirtmappings = OvirtMappings(network_mappings=[])
    for item in items:
        ovirtmappings.network_mappings.append(
            ResourceMappingItem(
                target_name=item.target_name,
                target_type=item.target_type,
                source_name=item.source_name,
            )
        )

    return ovirtmappings


def make_labels(vmimport_name):
    return f"vmimport.v2v.kubevirt.io/vmi-name={vmimport_name}"


class Source:
    vms = {
        "cirros": {
            "name": "v2v-cirros-vm-for-tests",
            "cpu_cores": 1,
            "cpu_sockets": 1,
            "cpu_threads": 1,
            "machine_type": "q35",
            "network_interfaces": 1,
            "volumes": 1,
        },
        "cirros-no-nics": {
            "name": "v2v-cirros-vm-no-nics",
            "cpu_cores": 1,
            "cpu_sockets": 1,
            "cpu_threads": 1,
            "machine_type": "q35",
            "network_interfaces": 0,
            "volumes": 1,
        },
        "cirros-2disks2nics": {
            "name": "v2v-cirros-vm-for-test-2disks2nics",
            "cpu_cores": 1,
            "cpu_sockets": 1,
            "cpu_threads": 1,
            "machine_type": "q35",
            "network_interfaces": 2,
            "volumes": 2,
        },
        "cirros-running": {
            "name": "v2v-cirros-vm-running",
            "cpu_cores": 1,
            "cpu_sockets": 1,
            "cpu_threads": 1,
            "machine_type": "q35",
            "network_interfaces": 1,
            "volumes": 1,
        },
        "vm63chars": {
            "name": "v2v-cirros-for-tests-char63long".ljust(63, "s"),
            "cpu_cores": 1,
            "cpu_sockets": 1,
            "cpu_threads": 1,
            "machine_type": "q35",
            "network_interfaces": 1,
            "volumes": 1,
        },
        "usbenabled": {
            "name": "v2v-cirros-vm-for-test-usb",
            "cpu_cores": 1,
            "cpu_sockets": 1,
            "cpu_threads": 1,
            "machine_type": "q35",
            "network_interfaces": 1,
            "volumes": 1,
            "expected_import_status": {
                "reason": VirtualMachineImport.MappingRulesConditionReason.MAPPING_FAILED,
                "status": VirtualMachineImport.Condition.Status.FALSE,
                "type": VirtualMachineImport.Condition.MAPPING_RULES_VERIFIED,
            },
        },
        "nodisk": {
            "name": "v2v-cirros-vm-for-test-nodisk",
            "cpu_cores": 1,
            "cpu_sockets": 1,
            "cpu_threads": 1,
            "machine_type": "q35",
            "network_interfaces": 1,
            "volumes": 1,
            "expected_import_status": {
                "reason": VirtualMachineImport.MappingRulesConditionReason.MAPPING_FAILED,
                "status": VirtualMachineImport.Condition.Status.FALSE,
                "type": VirtualMachineImport.Condition.MAPPING_RULES_VERIFIED,
            },
        },
        "notemplate": {
            "name": "v2v-for-tests-notemplate",
            "cpu_cores": 1,
            "cpu_sockets": 1,
            "cpu_threads": 1,
            "machine_type": "q35",
            "network_interfaces": 1,
            "volumes": 1,
            "expected_import_status": {
                "reason": VirtualMachineImport.SucceededConditionReason.VMTEMPLATE_MATCHING_FAILED,
                "status": VirtualMachineImport.Condition.Status.FALSE,
                "type": VirtualMachineImport.Condition.SUCCEEDED,
            },
        },
    }
