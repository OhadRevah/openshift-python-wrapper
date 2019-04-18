
import pytest

from resources.pod import Pod
from . import config


@pytest.fixture(scope='class')
def create_ovs_bridges_real_nics(request):
    """
    Create needed OVS bridges when setup is bare-metal
    """
    if not pytest.real_nics_env:
        return

    real_nics_bridge = config.BRIDGE_BR1

    def fin():
        """
        Remove created OVS bridges
        """
        for pod in pytest.privileged_pods:
            pod_object = Pod(name=pod, namespace=config.OPENSHIFT_SDN_NS)
            pod_container = pytest.privileged_pod_container
            pod_object.exec(command=f"{config.OVS_VSCTL_DEL_BR} {real_nics_bridge}", container=pod_container)
    request.addfinalizer(fin)

    for pod in pytest.privileged_pods:
        pod_object = Pod(name=pod, namespace=config.OPENSHIFT_SDN_NS)
        pod_name = pod
        pod_container = pytest.privileged_pod_container
        cmds = [
            f"{config.OVS_VSCTL_ADD_BR} {real_nics_bridge}",
            f"{config.OVS_VSCTL_ADD_PORT} {real_nics_bridge} {pytest.active_node_nics[pod_name][0]}",
        ]
        for cmd in cmds:
            assert pod_object.exec(command=cmd, container=pod_container)[0]


@pytest.fixture(scope='class')
def create_ovs_bridge_on_vxlan(request):
    """
    Create needed OVS bridges when setup is not bare-metal
    """
    if pytest.real_nics_env:
        return

    bridge_name_vxlan = config.BRIDGE_BR1
    vxlan_name = config.VXLAN_10

    def fin():
        """
        Remove created OVS bridges
        """
        for pod in pytest.privileged_pods:
            pod_object = Pod(name=pod, namespace=config.OPENSHIFT_SDN_NS)
            pod_container = pytest.privileged_pod_container
            pod_object.exec(command=f"{config.OVS_VSCTL_DEL_BR} {bridge_name_vxlan}", container=pod_container)
    request.addfinalizer(fin)

    for pod in pytest.privileged_pods:
        pod_object = Pod(name=pod, namespace=config.OPENSHIFT_SDN_NS)
        pod_container = pytest.privileged_pod_container
        node_name = pod_object.node()
        cmds = [f"{config.OVS_VSCTL_ADD_BR} {bridge_name_vxlan}"]
        for name, ip in pytest.nodes_network_info.items():
            if name != node_name:
                cmd = (
                    f"{config.OVS_VSCTL_ADD_PORT} {bridge_name_vxlan} {vxlan_name} -- "
                    f"set Interface {vxlan_name} type=vxlan options:remote_ip={ip}"
                )
                cmds.insert(1, cmd)
                break

        for cmd in cmds:
            assert pod_object.exec(command=cmd, container=pod_container)[0]


@pytest.fixture(scope='class')
def attach_ovs_bridge_to_bond():
    """
    Create bridge and attach the BOND to it
    """
    if not pytest.bond_support_env:
        return

    bond_name = config.BOND_1
    bond_bridge = config.BRIDGE_BR1BOND
    for pod in pytest.privileged_pods:
        pod_object = Pod(name=pod, namespace=config.OPENSHIFT_SDN_NS)
        pod_container = pytest.privileged_pod_container
        cmds = [
            f"{config.OVS_VSCTL_ADD_BR} {bond_bridge}",
            f"{config.OVS_VSCTL_ADD_PORT} {bond_bridge} {bond_name}"
        ]
        for cmd in cmds:
            assert pod_object.exec(command=cmd, container=pod_container)[0]
