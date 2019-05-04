import pytest

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
            pod_container = pod.containers()[0].name
            pod.execute(command=["ip", "link", "del", bond_name], container=pod_container)
    request.addfinalizer(fin)

    bond_commands = [
        ["ip", "link", "add", bond_name, "type", "bond"],
        ["ip", "link", "set", bond_name, "type", "bond", "miimon", "100", "mode", "active-backup"]
    ]
    for pod in pytest.privileged_pods:
        pod_container = pod.containers()[0].name
        for cmd in bond_commands:
            pod.execute(command=cmd, container=pod_container)

        for nic in pytest.active_node_nics[pod.name][1:3]:
            pod.execute(command=["ip", "link", "set", nic, "down"], container=pod_container)
            pod.execute(
                command=["ip", "link", "set", nic, "master", bond_name], container=pod_container
            )
            pod.execute(command=["ip", "link", "set", nic, "up"], container=pod_container)

        pod.execute(
            command=["ip", "link", "set", bond_name, "down"],
            container=pod_container
        )
        out = pod.execute(command=["ip", "link", "show", bond_name], container=pod_container)
        assert "state UP" in out
