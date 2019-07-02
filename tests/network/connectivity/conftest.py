import pytest


@pytest.fixture(scope="class")
def create_bond(request, network_utility_pods, bond_supported, nodes_active_nics):
    """
    Create BOND if setup support BOND
    """
    bond_name = "bond1"

    if not bond_supported:
        return

    def fin():
        """
        Remove created BOND
        """
        for pod in network_utility_pods:
            pod_container = pod.containers()[0].name
            pod.execute(
                command=["ip", "link", "del", bond_name], container=pod_container
            )

    request.addfinalizer(fin)

    bond_commands = [
        ["ip", "link", "add", bond_name, "type", "bond"],
        [
            "ip",
            "link",
            "set",
            bond_name,
            "type",
            "bond",
            "miimon",
            "100",
            "mode",
            "active-backup",
        ],
    ]
    for pod in network_utility_pods:
        pod_container = pod.containers()[0].name
        node_name = pod.node.name
        for cmd in bond_commands:
            pod.execute(command=cmd, container=pod_container)

        for nic in nodes_active_nics[node_name][2:4]:
            pod.execute(
                command=["ip", "link", "set", nic, "down"], container=pod_container
            )
            pod.execute(
                command=["ip", "link", "set", nic, "master", bond_name],
                container=pod_container,
            )
            pod.execute(
                command=["ip", "link", "set", nic, "up"], container=pod_container
            )

        pod.execute(
            command=["ip", "link", "set", bond_name, "up"], container=pod_container
        )
        out = pod.execute(
            command=["ip", "link", "show", bond_name], container=pod_container
        )
        assert "state UP" in out
