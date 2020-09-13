from resources.virtual_machine_import import OvirtMappings, ResourceMappingItem


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
    }
