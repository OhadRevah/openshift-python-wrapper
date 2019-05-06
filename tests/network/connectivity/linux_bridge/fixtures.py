import pytest

from tests import utils as test_utils
from . import config


@pytest.fixture(scope='class')
def create_linux_bridges_real_nics(request, nodes_active_nics, is_bare_metal):
    """
    Create needed linux bridges when setup is bare-metal
    """
    if not is_bare_metal:
        return

    bridge_name = test_utils.get_fixture_val(request=request, attr_name="bridge_name")

    def fin():
        """
        Remove created linux bridges
        """
        for pod in pytest.privileged_pods:
            pod_container = pod.containers()[0].name
            pod.execute(command=["ip", "link", "del", bridge_name], container=pod_container)
    request.addfinalizer(fin)

    for pod in pytest.privileged_pods:
        pod_container = pod.containers()[0].name
        node_name = pod.node().name
        cmds = [
            ["ip", "link", "add", bridge_name, "type", "bridge"],
            ["ip", "link", "set", bridge_name, "type", "bridge", "vlan_filtering", "1"],
            ["ip", "link", "set", "dev", bridge_name, "up"],
            ["ip", "link", "set", "dev", nodes_active_nics[node_name][0], "master", bridge_name],
        ]
        for cmd in cmds:
            pod.execute(command=cmd, container=pod_container)


@pytest.fixture(scope='class')
def create_linux_bridge_on_vxlan(request, schedulable_node_ips, is_bare_metal):
    """
    Create needed linux bridges when setup is not bare-metal
    """
    if is_bare_metal:
        return

    bridge_name = test_utils.get_fixture_val(request=request, attr_name="bridge_name")
    vxlan_name = test_utils.get_fixture_val(request=request, attr_name="vxlan_name")

    def fin():
        """
        Remove created linux bridges
        """
        for pod in pytest.privileged_pods:
            pod_container = pod.containers()[0].name
            cmds = [
                ["ip", "link", "del", bridge_name],
                ["ip", "link", "del", vxlan_name],
            ]
            for cmd in cmds:
                pod.execute(command=cmd, container=pod_container)
    request.addfinalizer(fin)

    for idx, pod in enumerate(pytest.privileged_pods):
        pod_container = pod.containers()[0].name
        node_name = pod.node()
        cmds = [
            ["ip", "link", "add", bridge_name, "type", "bridge"],
            ["ip", "link", "set", bridge_name, "type", "bridge", "vlan_filtering", "1"],
            ["ip", "link", "set", vxlan_name, "master", bridge_name],
            ["ip", "link", "set", "up", vxlan_name],
            ["ip", "link", "set", "up", bridge_name],
        ]
        for name, ip in schedulable_node_ips.items():
            if name != node_name:
                cmd = [
                    "ip", "link", "add", vxlan_name, "type", "vxlan", "id",
                    config.VXLAN_IDS[idx], "remote", ip, "dstport", "4790"
                ]
                cmds.insert(1, cmd)
                break

        for cmd in cmds:
            pod.execute(command=cmd, container=pod_container)


@pytest.fixture(scope='class')
def attach_linux_bridge_to_bond(request, bond_supported):
    """
    Create bridge and attach the BOND to it
    """
    if not bond_supported:
        return

    bond_name = test_utils.get_fixture_val(request=request, attr_name="bond_name")
    bond_bridge = test_utils.get_fixture_val(request=request, attr_name="bond_bridge")

    for pod in pytest.privileged_pods:
        pod_container = pod.containers()[0].name
        cmds = [
            ["ip", "link", "add", bond_bridge, "type", "bridge"],
            ["ip", "link", "set", "dev", bond_bridge, "up"],
            ["ip", "link", "set", "dev", bond_name, "master", bond_bridge]
        ]
        for cmd in cmds:
            pod.execute(command=cmd, container=pod_container)
