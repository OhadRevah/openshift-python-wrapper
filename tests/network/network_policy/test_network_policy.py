"""
Network policy tests
"""

import pytest
from resources.network_policy import NetworkPolicy
from utilities import console
from utilities.infra import create_ns
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    CommandExecFailed,
    VirtualMachineForTests,
    fedora_vm_body,
    vm_console_run_commands,
    wait_for_vm_interfaces,
)


class VirtualMachineMasquerade(VirtualMachineForTests):
    def __init__(self, name, namespace, node_selector, client=None, teardown=True):
        super().__init__(
            name=name,
            namespace=namespace,
            node_selector=node_selector,
            client=client,
            cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
            teardown=teardown,
        )

    def to_dict(self):
        self.body = fedora_vm_body(name=self.name)
        res = super().to_dict()
        vm_interfaces = res["spec"]["template"]["spec"]["domain"]["devices"][
            "interfaces"
        ]
        for iface in vm_interfaces:
            if "masquerade" in iface.keys():
                iface["ports"] = [
                    {"name": "http80", "port": 80, "protocol": "TCP"},
                    {"name": "http81", "port": 81, "protocol": "TCP"},
                ]
        return res


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
def namespace_1(unprivileged_client, kmp_vm_label, default_client):
    yield from create_ns(
        client=unprivileged_client,
        name="network-policy-test-1",
        kmp_vm_label=kmp_vm_label,
        admin_client=default_client,
    )


@pytest.fixture(scope="module")
def namespace_2(unprivileged_client, kmp_vm_label, default_client):
    yield from create_ns(
        client=unprivileged_client,
        name="network-policy-test-2",
        kmp_vm_label=kmp_vm_label,
        admin_client=default_client,
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
        name="allow-all-http-ports", namespace=namespace_1.name, ports=[80, 81]
    ) as np:
        yield np


@pytest.fixture()
def allow_http80_port(namespace_1):
    with ApplyNetworkPolicy(
        name="allow-http80-port", namespace=namespace_1.name, ports=[80]
    ) as np:
        yield np


@pytest.fixture(scope="module")
def network_policy_vma(namespace_1, worker_node1, unprivileged_client):
    name = "vma"
    with VirtualMachineMasquerade(
        namespace=namespace_1.name,
        name=name,
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
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def running_network_policy_vma(network_policy_vma):
    network_policy_vma.vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=network_policy_vma.vmi)
    yield network_policy_vma


@pytest.fixture(scope="module")
def running_network_policy_vmb(network_policy_vmb):
    network_policy_vmb.vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=network_policy_vmb.vmi)
    yield network_policy_vmb


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
        vm_console_run_commands(
            console_impl=console.Fedora,
            vm=network_policy_vmb,
            commands=[
                f"curl --head {dst_ip}:{port} --connect-timeout 5" for port in [80, 81]
            ],
            timeout=10,
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
    vm_console_run_commands(
        console_impl=console.Fedora,
        vm=network_policy_vmb,
        commands=[
            f"curl --head {dst_ip}:{port} --connect-timeout 5" for port in [80, 81]
        ],
        timeout=10,
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
    vm_console_run_commands(
        console_impl=console.Fedora,
        vm=network_policy_vmb,
        commands=[f"curl --head {dst_ip}:80 --connect-timeout 5"],
        timeout=10,
    )

    with pytest.raises(CommandExecFailed):
        vm_console_run_commands(
            console_impl=console.Fedora,
            vm=network_policy_vmb,
            commands=[f"curl --head {dst_ip}:81 --connect-timeout 5"],
            timeout=10,
        )
