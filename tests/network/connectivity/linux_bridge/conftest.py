import pytest


@pytest.fixture(scope="module")
def attach_linux_bridge_to_bond(network_utility_pods, bond_supported):
    """
    Create bridge and attach the BOND to it
    """
    if not bond_supported:
        return

    bond_name = "bond1"
    bond_bridge = "br1bond"

    for pod in network_utility_pods:
        pod_container = pod.containers()[0].name
        cmds = [
            ["ip", "link", "add", bond_bridge, "type", "bridge"],
            ["ip", "link", "set", "dev", bond_bridge, "up"],
            ["ip", "link", "set", "dev", bond_name, "master", bond_bridge]
        ]
        for cmd in cmds:
            pod.execute(command=cmd, container=pod_container)
