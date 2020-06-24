import logging

import pytest
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def vma(schedulable_nodes, namespace, unprivileged_client, node_with_bond):
    name = "vma"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=node_with_bond,
        client=unprivileged_client,
        body=fedora_vm_body(name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def vmb(schedulable_nodes, namespace, unprivileged_client, node_with_bond):
    name = "vmb"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=next(
            filter(lambda node: node.name != node_with_bond, schedulable_nodes)
        ).name,
        client=unprivileged_client,
        body=fedora_vm_body(name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def running_vma(vma):
    vma.vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vma.vmi)
    return vma


@pytest.fixture(scope="module")
def running_vmb(vmb):
    vmb.vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmb.vmi)
    return vmb


def get_interface_by_attribute(all_connections, att):
    connection_array = all_connections.split("\n")
    if att in connection_array:
        iface_name_string = connection_array[connection_array.index(att) - 1]
        iface_name = iface_name_string.split(":")[1]
        return iface_name


@pytest.fixture(scope="module")
def bond_and_privileged_pod(network_utility_pods):
    for pod in network_utility_pods:
        all_connections = pod.execute(
            command=[
                "bash",
                "-c",
                'nmcli -g name con show | \
                xargs -i nmcli -t -f connection.interface-name,ovs-port.bond-mode connection show "{}"',
            ],
        )

        bond_mode_string = "ovs-port.bond-mode:balance-slb"
        bond = get_interface_by_attribute(
            all_connections=all_connections, att=bond_mode_string
        )

        if bond:
            return bond, pod

    return None, None


@pytest.fixture(scope="module")
def privileged_pod(bond_and_privileged_pod):
    _, pod = bond_and_privileged_pod
    return pod


@pytest.fixture(scope="module")
def bond(bond_and_privileged_pod):
    bond, _ = bond_and_privileged_pod
    return bond


@pytest.fixture(scope="module")
def node_with_bond(privileged_pod):
    return privileged_pod.node.name


@pytest.fixture(scope="module")
def slave(privileged_pod, bond, node_with_bond):
    all_connections = privileged_pod.execute(
        command=[
            "bash",
            "-c",
            'nmcli -g name con show | \
            xargs -i nmcli -t -f connection.interface-name,connection.master connection show "{}"',
        ],
    )

    bond_string = f"connection.master:{bond}"
    slave = get_interface_by_attribute(all_connections=all_connections, att=bond_string)

    assert slave is not None, f"OVS Bond {bond} on node {node_with_bond} has no slaves"
    return slave


@pytest.fixture(scope="module")
def skip_when_no_bond(bond):
    if not bond:
        pytest.skip(msg="The test requires at least one node with an OVS bond")


@pytest.fixture(scope="module")
def disconnected_slave(privileged_pod, slave, bond):
    LOGGER.info(f"Disconnecting slave {slave} of bond {bond}")
    privileged_pod.execute(command=["bash", "-c", f"nmcli dev disconnect {slave}"])

    yield slave

    LOGGER.info(f"Reconnecting slave {slave} of bond {bond}")
    privileged_pod.execute(command=["bash", "-c", f"nmcli dev connect {slave}"])
