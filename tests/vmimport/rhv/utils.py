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
