from resources.virtual_machine_import import OvirtMappings, ResourceMappingItem


POD_MAPPING = OvirtMappings(
    network_mappings=[
        ResourceMappingItem(
            target_name="pod", target_type="pod", source_name="ovirtmgmt/ovirtmgmt"
        )
    ]
)
