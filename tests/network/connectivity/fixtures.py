
import pytest

from resources.pod import Pod
from . import config


@pytest.fixture(scope='class')
def create_bond(request):
    """
    Create BOND if setup support BOND
    """
    bond_name = config.BOND_1

    if not pytest.bond_support_env:
        return

    def fin():
        """
        Remove created BOND
        """
        for pod in pytest.privileged_pods:
            pod_object = Pod(name=pod, namespace=config.OPENSHIFT_SDN_NS)
            pod_container = pytest.privileged_pod_container
            pod_object.exec(command=f"ip link del {bond_name}", container=pod_container)
    request.addfinalizer(fin)

    bond_commands = [
        f"ip link add {bond_name} type bond", f"ip link set {bond_name} type bond miimon 100 mode active-backup"
    ]
    for pod in pytest.privileged_pods:
        pod_object = Pod(name=pod, namespace=config.OPENSHIFT_SDN_NS)
        pod_name = pod
        pod_container = pytest.privileged_pod_container
        for cmd in bond_commands:
            assert pod_object.exec(command=cmd, container=pod_container)[0]

        for nic in pytest.active_node_nics[pod_name][1:3]:
            assert pod_object.exec(
                command=config.IP_LINK_INTERFACE_DOWN.format(interface=nic), container=pod_container
            )[0]

            assert pod_object.exec(
                command=f"ip link set {nic} master {bond_name}", container=pod_container
            )[0]

            assert pod_object.exec(
                command=config.IP_LINK_INTERFACE_UP.format(interface=nic), container=pod_container
            )[0]

        assert pod_object.exec(
            command=config.IP_LINK_INTERFACE_UP.format(interface=bond_name), container=pod_container
        )[0]

        res, out = pod_object.exec(command=f"ip link show {bond_name}", container=pod_container)

        assert res
        assert "state UP" in out
