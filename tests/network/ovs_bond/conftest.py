import logging

import pytest

from utilities.exceptions import CommandExecFailed
from utilities.infra import run_ssh_commands
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def ovs_bond_vma(schedulable_nodes, namespace, unprivileged_client, node_with_bond):
    name = "vma"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=node_with_bond,
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def ovs_bond_vmb(schedulable_nodes, namespace, unprivileged_client, node_with_bond):
    name = "vmb"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=next(
            filter(lambda node: node.name != node_with_bond, schedulable_nodes)
        ).name,
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def running_ovs_bond_vma(ovs_bond_vma):
    return running_vm(vm=ovs_bond_vma)


@pytest.fixture(scope="module")
def running_ovs_bond_vmb(ovs_bond_vmb):
    return running_vm(vm=ovs_bond_vma)


def get_interface_by_attribute(all_connections, att):
    connection_array = all_connections.split("\n")
    if att in connection_array:
        iface_name_string = connection_array[connection_array.index(att) - 1]
        iface_name = iface_name_string.split(":")[1]
        return iface_name


@pytest.fixture(scope="module")
def bond_and_privileged_pod(workers_ssh_executors, utility_pods):
    """
    Get OVS BOND from the worker, if OVS BOND not exists the tests should be skipped.
    """
    skip_msg = "BOND is not configured on the workers on primary interface"
    for pod in utility_pods:
        node_executor = workers_ssh_executors[pod.node.name]
        try:
            # TODO: use rrmngmnt to get info from nmcli
            all_connections = _all_connection(node_executor=node_executor)
            bond = get_interface_by_attribute(
                all_connections=all_connections[0], att="ovs-port.bond-mode:balance-slb"
            )

            if bond:
                return bond, pod

            pytest.skip(msg=skip_msg)
        except CommandExecFailed:
            pytest.skip(msg=skip_msg)
            break


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
def slave(workers_ssh_executors, privileged_pod, bond, node_with_bond):
    node_executor = workers_ssh_executors[privileged_pod.node.name]
    all_connections = _all_connection(node_executor=node_executor)

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


def _all_connection(node_executor):
    return run_ssh_commands(
        host=node_executor,
        commands=[
            [
                "bash",
                "-c",
                'nmcli -g name con show | \
                xargs -i nmcli -t -f connection.interface-name,ovs-port.bond-mode connection show "{}"',
            ]
        ],
    )[0]