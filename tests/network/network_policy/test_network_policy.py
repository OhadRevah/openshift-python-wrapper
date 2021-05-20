"""
Network policy tests
"""
import shlex

import pytest
from ocp_resources.network_policy import NetworkPolicy

from utilities.exceptions import CommandExecFailed
from utilities.infra import create_ns, run_ssh_commands
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


PORT_80 = 80
PORT_81 = 81
CURL_TIMEOUT = 5


class ApplyNetworkPolicy(NetworkPolicy):
    def __init__(self, name, namespace, ports=None, teardown=True):
        super().__init__(name=name, namespace=namespace, teardown=teardown)
        self.ports = ports

    def to_dict(self):
        res = super().to_dict()
        _ports = []
        if self.ports:
            for port in self.ports:
                _ports.append({"protocol": "TCP", "port": port})

        res["spec"] = {"podSelector": {}}
        if _ports:
            res["spec"]["ingress"] = [{"ports": _ports}]
        return res


@pytest.fixture(scope="module")
def namespace_1(unprivileged_client):
    yield from create_ns(
        client=unprivileged_client,
        name="network-policy-test-1",
    )


@pytest.fixture(scope="module")
def namespace_2(unprivileged_client):
    yield from create_ns(
        client=unprivileged_client,
        name="network-policy-test-2",
    )


@pytest.fixture()
def deny_all_http_ports(namespace_1):
    with ApplyNetworkPolicy(
        name="deny-all-http-ports", namespace=namespace_1.name
    ) as np:
        yield np


@pytest.fixture()
def allow_all_http_ports(namespace_1):
    with ApplyNetworkPolicy(
        name="allow-all-http-ports",
        namespace=namespace_1.name,
        ports=[PORT_80, PORT_81],
    ) as np:
        yield np


@pytest.fixture()
def allow_http80_port(namespace_1):
    with ApplyNetworkPolicy(
        name="allow-http80-port", namespace=namespace_1.name, ports=[PORT_80]
    ) as np:
        yield np


@pytest.fixture(scope="module")
def network_policy_vma(namespace_1, worker_node1, unprivileged_client):
    name = "vma"
    with VirtualMachineForTests(
        namespace=namespace_1.name,
        name=name,
        body=fedora_vm_body(name=name),
        node_selector=worker_node1.name,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def network_policy_vmb(namespace_2, worker_node1, unprivileged_client):
    name = "vmb"
    with VirtualMachineForTests(
        namespace=namespace_2.name,
        name=name,
        node_selector=worker_node1.name,
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def running_network_policy_vma(network_policy_vma):
    return running_vm(vm=network_policy_vma)


@pytest.fixture(scope="module")
def running_network_policy_vmb(network_policy_vmb):
    return running_vm(vm=network_policy_vmb)


@pytest.mark.polarion("CNV-369")
def test_network_policy_deny_all_http(
    skip_rhel7_workers,
    deny_all_http_ports,
    network_policy_vma,
    network_policy_vmb,
    running_network_policy_vma,
    running_network_policy_vmb,
):
    dst_ip = network_policy_vma.vmi.virt_launcher_pod.instance.status.podIP
    with pytest.raises(CommandExecFailed):
        run_ssh_commands(
            host=network_policy_vmb.ssh_exec,
            commands=[
                shlex.split(
                    f"curl --head {dst_ip}:{port} --connect-timeout {CURL_TIMEOUT}"
                )
                for port in [PORT_80, PORT_81]
            ],
        )


@pytest.mark.polarion("CNV-369")
def test_network_policy_allow_all_http(
    skip_rhel7_workers,
    allow_all_http_ports,
    network_policy_vma,
    network_policy_vmb,
    running_network_policy_vma,
    running_network_policy_vmb,
):
    dst_ip = network_policy_vma.vmi.virt_launcher_pod.instance.status.podIP
    run_ssh_commands(
        host=network_policy_vmb.ssh_exec,
        commands=[
            shlex.split(f"curl --head {dst_ip}:{port} --connect-timeout {CURL_TIMEOUT}")
            for port in [PORT_80, PORT_81]
        ],
    )


@pytest.mark.polarion("CNV-369")
def test_network_policy_allow_http80(
    skip_rhel7_workers,
    allow_http80_port,
    network_policy_vma,
    network_policy_vmb,
    running_network_policy_vma,
    running_network_policy_vmb,
):
    dst_ip = network_policy_vma.vmi.virt_launcher_pod.instance.status.podIP
    run_ssh_commands(
        host=network_policy_vmb.ssh_exec,
        commands=[
            shlex.split(
                f"curl --head {dst_ip}:{PORT_80} --connect-timeout {CURL_TIMEOUT}"
            )
        ],
    )

    with pytest.raises(CommandExecFailed):
        run_ssh_commands(
            host=network_policy_vmb.ssh_exec,
            commands=[
                shlex.split(
                    f"curl --head {dst_ip}:{PORT_81} --connect-timeout {CURL_TIMEOUT}"
                )
            ],
        )
