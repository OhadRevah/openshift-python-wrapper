import pytest

from . import config


@pytest.fixture(scope='class')
def create_ovs_bridges_real_nics(request, nodes_active_nics, is_bare_metal):
    """
    Create needed OVS bridges when setup is bare-metal
    """
    if not is_bare_metal:
        return

    real_nics_bridge = config.BRIDGE_BR1

    def fin():
        """
        Remove created OVS bridges
        """
        for pod in pytest.privileged_pods:
            pod_container = pod.containers()[0].name
            pod.execute(
                command=["ovs-vsctl", "del-br", real_nics_bridge], container=pod_container
            )
    request.addfinalizer(fin)

    for pod in pytest.privileged_pods:
        pod_container = pod.containers()[0].name
        node_name = pod.node().name
        cmds = [
            ["ovs-vsctl", "add-br", real_nics_bridge],
            ["ovs-vsctl", "add-port", real_nics_bridge, nodes_active_nics[node_name][0]],
        ]
        for cmd in cmds:
            pod.execute(command=cmd, container=pod_container)


@pytest.fixture(scope='class')
def create_ovs_bridge_on_vxlan(request, schedulable_node_ips, is_bare_metal):
    """
    Create needed OVS bridges when setup is not bare-metal
    """
    if is_bare_metal:
        return

    bridge_name_vxlan = config.BRIDGE_BR1
    vxlan_name = config.VXLAN_10

    def fin():
        """
        Remove created OVS bridges
        """
        for pod in pytest.privileged_pods:
            pod_container = pod.containers()[0].name
            pod.execute(
                command=["ovs-vsctl", "del-br", bridge_name_vxlan], container=pod_container
            )
    request.addfinalizer(fin)

    for pod in pytest.privileged_pods:
        pod_container = pod.containers()[0].name
        node_name = pod.node()
        cmds = ["ovs-vsctl", "add-br", bridge_name_vxlan]
        for name, ip in schedulable_node_ips.items():
            if name != node_name:
                cmd = (
                    [
                        "ovs-vsctl", "add-port", bridge_name_vxlan, vxlan_name, " -- ",
                        "set", "Interface", vxlan_name, "type=vxlan", f"options:remote_ip={ip}"
                    ]
                )
                cmds.insert(1, cmd)
                break

        for cmd in cmds:
            pod.execute(command=cmd, container=pod_container)


@pytest.fixture(scope='class')
def attach_ovs_bridge_to_bond(bond_supported):
    """
    Create bridge and attach the BOND to it
    """
    if not bond_supported:
        return

    bond_name = config.BOND_1
    bond_bridge = config.BRIDGE_BR1BOND
    for pod in pytest.privileged_pods:
        pod_container = pod.containers()[0].name
        cmds = [
            ["ovs-vsctl", "add-br", bond_bridge],
            ["ovs-vsctl", "add-port", bond_bridge, bond_name]
        ]
        for cmd in cmds:
            pod.execute(command=cmd, container=pod_container)
