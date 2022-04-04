from ocp_resources.node_network_state import NodeNetworkState


def assert_bridge_and_vms_on_same_node(vm_a, vm_b, bridge):
    for vm in [vm_a, vm_b]:
        assert vm.vmi.node.name == bridge.node_selector


def assert_node_is_marked_by_bridge(bridge_nad, vm):
    for bridge_annotation in bridge_nad.instance.metadata.annotations.values():
        assert bridge_annotation in vm.vmi.node.instance.status.capacity.keys()
        assert bridge_annotation in vm.vmi.node.instance.status.allocatable.keys()


def assert_nmstate_bridge_creation(bridge):
    nns = NodeNetworkState(name=bridge.node_selector)
    assert nns.get_interface(
        name=bridge.bridge_name
    ), f"Nmstate bridge: {bridge.bridge_name} not found"
