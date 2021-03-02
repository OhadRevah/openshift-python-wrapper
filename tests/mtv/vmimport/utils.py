from ocp_resources.virtual_machine_import import VirtualMachineImport

from utilities.storage import get_storage_class_dict_from_matrix


class ProviderMappings:
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
        target_volume_mode=None,
        target_access_modes=None,
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
        self.target_volume_mode = target_volume_mode
        self.target_access_modes = target_access_modes


# Same as get_storage_class_dict_from_matrix but return None if not found
def get_storage_class_dict_from_matrix_or_none(storage_class):
    try:
        return get_storage_class_dict_from_matrix(storage_class=storage_class)[
            storage_class
        ]
    except ValueError:
        return None


def storage_mapping_by_source_vm_disks_storage_name(
    storage_classes, source_volumes_config
):
    storage_mapping_items = []
    for storage_class_index, source_volume_config in enumerate(source_volumes_config):
        _sc_name = storage_classes[storage_class_index]
        _sc_config = get_storage_class_dict_from_matrix_or_none(storage_class=_sc_name)
        storage_mapping_items.append(
            ResourceMappingItem(
                source_name=source_volume_config["storage_name"],
                target_name=_sc_name,
                target_volume_mode=_sc_config["volume_mode"] if _sc_config else None,
                target_access_modes=_sc_config["access_mode"] if _sc_config else None,
                # the none default sc we use may use the default access/vol mode
            )
        )
    return storage_mapping_items


def network_mappings(items):
    provider_mappings = ProviderMappings(network_mappings=[])
    for item in items:
        provider_mappings.network_mappings.append(item)
    return provider_mappings


def make_labels(vmimport_name):
    return f"vmimport.v2v.kubevirt.io/vmi-name={vmimport_name}"


class Source:
    default_network_names = {
        "ovirt": ["ovirtmgmt/ovirtmgmt", "vm/vm"],
        "vmware": ["VM Network", "Mgmt Network"],
    }
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
        "cirros2": {
            "name": "v2v-cirros-vm-for-tests2",
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
        "cirros-3disks-rhev-blue-01.rdu2.scalelab.redhat.com": {
            "name": "v2v-cirros-vm-for-test-3disks",
            "cpu_cores": 1,
            "cpu_sockets": 1,
            "cpu_threads": 1,
            "machine_type": "q35",
            "network_interfaces": 1,
            "volumes": 3,
            "volumes_details": [
                {
                    "disk_name": "v2v-cirros-vm-for-test-3disks_v2v-fc",
                    "storage_name": "v2v-fc",
                },  # Rhv: storage domain, VMWare: datastore
                {
                    "disk_name": "v2v-cirros-vm-for-test-3disks_v2v-iscsi",
                    "storage_name": "v2v-iscsi",
                },
                {
                    "disk_name": "v2v-cirros-vm-for-test-3disks_hosted_storage",
                    "storage_name": "hosted_storage",
                },
            ],
        },
        "cirros-3disks-rhev-node-05.rdu2.scalelab.redhat.com": {
            "name": "v2v-3disks",
            "cpu_cores": 1,
            "cpu_sockets": 1,
            "cpu_threads": 1,
            "machine_type": "q35",
            "network_interfaces": 1,
            "volumes": 3,
            "volumes_details": [
                {
                    "disk_name": "Hard disk 1",
                    "storage_name": "v2v_general_porpuse_ISCSI_DC",
                },
                {
                    "disk_name": "Hard disk 2",
                    "storage_name": "rhv-v2v-performance-testing",
                },
                {
                    "disk_name": "Hard disk 3",
                    "storage_name": "mtv-scale-datastore",
                },
            ],
        },
        "cirros-3disks-env-rhv44-mgr.cfme2.lab.eng.rdu2.redhat.com": {
            "name": "v2v-3disks",
            "cpu_cores": 1,
            "cpu_sockets": 1,
            "cpu_threads": 1,
            "machine_type": "q35",
            "network_interfaces": 0,
            "volumes": 3,
            "volumes_details": [
                {
                    "disk_name": "RHEL8-KK_Disk1_v2v-3disks",
                    "storage_name": "templates_netapp_rdu_02",
                },  # Rhv: storage domain, VMWare: datastore
                {
                    "disk_name": "v2v-3disks_Disk1",
                    "storage_name": "env-rhv44-02-nfs-data",
                },
                {
                    "disk_name": "v2v-3disks_Disk2",
                    "storage_name": "iscsi_data_netapp_rdu_02",
                },
            ],
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
        "no-vnic-profile": {
            "name": "v2v-cirros-vm-for-test-no-vnic-profile",
            "cpu_cores": 1,
            "cpu_sockets": 1,
            "cpu_threads": 1,
            "machine_type": "q35",
            "network_interfaces": 0,
            "volumes": 1,
        },
    }
