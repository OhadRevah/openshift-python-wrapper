
import pytest

from resources.pod import Pod
from tests import utils as test_utils
from . import config


@pytest.fixture(scope='class')
def create_linux_bridges_real_nics(request):
    """
    Create needed linux bridges when setup is bare-metal
    """
    if not pytest.real_nics_env:
        return

    bridge_name = test_utils.get_fixture_val(request=request, attr_name="bridge_name")

    def fin():
        """
        Remove created linux bridges
        """
        for pod in pytest.privileged_pods:
            pod_object = Pod(name=pod, namespace=pytest.privileged_pods_ns)
            pod_container = pytest.privileged_pod_container
            pod_object.exec(command=f"ip_link_del {bridge_name}", container=pod_container)
    request.addfinalizer(fin)

    for idx, pod in enumerate(pytest.privileged_pods):
        pod_object = Pod(name=pod, namespace=pytest.privileged_pods_ns)
        pod_name = pod
        pod_container = pytest.privileged_pod_container
        cmds = [
            f"ip link add {bridge_name} type bridge",
            f"ip link set {bridge_name} type bridge vlan_filtering 1",
            f"ip link set dev {bridge_name} up",
            f"ip link set dev {pytest.active_node_nics[pod_name][0]} master {bridge_name}",
        ]
        for cmd in cmds:
            assert pod_object.exec(command=cmd, container=pod_container)[0]


@pytest.fixture(scope='class')
def create_linux_bridge_on_vxlan(request):
    """
    Create needed linux bridges when setup is not bare-metal
    """
    if pytest.real_nics_env:
        return

    bridge_name = test_utils.get_fixture_val(request=request, attr_name="bridge_name")
    vxlan_name = test_utils.get_fixture_val(request=request, attr_name="vxlan_name")

    def fin():
        """
        Remove created linux bridges
        """
        for pod in pytest.privileged_pods:
            pod_object = Pod(name=pod, namespace=pytest.privileged_pods_ns)
            pod_container = pytest.privileged_pod_container
            cmds = [
                f"ip link del {bridge_name}",
                f"ip link del {vxlan_name}",
            ]
            for cmd in cmds:
                pod_object.exec(command=cmd, container=pod_container)
    request.addfinalizer(fin)

    for idx, pod in enumerate(pytest.privileged_pods):
        pod_object = Pod(name=pod, namespace=pytest.privileged_pods_ns)
        pod_container = pytest.privileged_pod_container
        node_name = pod_object.node()
        cmds = [
            f"ip link add {bridge_name} type bridge",
            f"ip link set {bridge_name} type bridge vlan_filtering 1",
            f"ip link set {vxlan_name} master {bridge_name}",
            f"ip link set up {vxlan_name}",
            f"ip link set up {bridge_name}",
        ]
        for name, ip in pytest.nodes_network_info.items():
            if name != node_name:
                cmd = f"ip link add {vxlan_name} type vxlan id {config.VXLAN_IDS[idx]} remote {ip} dstport 4790"
                cmds.insert(1, cmd)
                break

        for cmd in cmds:
            assert pod_object.exec(command=cmd, container=pod_container)[0]


@pytest.fixture(scope='class')
def attach_linux_bridge_to_bond(request):
    """
    Create bridge and attach the BOND to it
    """
    if not pytest.bond_support_env:
        return

    bond_name = test_utils.get_fixture_val(request=request, attr_name="bond_name")
    bond_bridge = test_utils.get_fixture_val(request=request, attr_name="bond_bridge")

    for pod in pytest.privileged_pods:
        pod_object = Pod(name=pod, namespace=pytest.privileged_pods_ns)
        pod_container = pytest.privileged_pod_container
        cmds = [
            f"ip link add {bond_bridge} type bridge",
            f"ip link set dev {bond_bridge} up",
            f"ip link set dev {bond_name} master {bond_bridge}"
        ]
        for cmd in cmds:
            assert pod_object.exec(command=cmd, container=pod_container)[0]
