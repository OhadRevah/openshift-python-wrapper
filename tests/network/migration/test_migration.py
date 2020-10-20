# -*- coding: utf-8 -*-
"""
Network Migration test
"""

import logging

import pytest
import tests.network.utils as network_utils
from resources.virtual_machine import VirtualMachineInstanceMigration
from utilities import console
from utilities.network import (
    LINUX_BRIDGE,
    cloud_init_network_data,
    get_hosts_common_ports,
    get_vmi_ip_v4_by_name,
    network_nad,
)
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    enable_ssh_service_in_vm,
    fedora_vm_body,
    vm_console_run_commands,
    wait_for_vm_interfaces,
)


BR1TEST = "br1test"
LOGGER = logging.getLogger(__name__)


def http_port_accessible(vm, server_ip, server_port):
    vm_console_run_commands(
        console_impl=console.Fedora,
        vm=vm,
        commands=[f"curl --head {server_ip}:{server_port} --connect-timeout 5"],
        timeout=10,
    )


class BridgedFedoraVirtualMachine(VirtualMachineForTests):
    def __init__(
        self,
        name,
        namespace,
        client=None,
        interfaces=None,
        networks=None,
        node_selector=None,
        cloud_init_data=None,
    ):
        super().__init__(
            name=name,
            namespace=namespace,
            client=client,
            interfaces=interfaces,
            networks=networks,
            node_selector=node_selector,
            cloud_init_data=cloud_init_data,
        )

    def to_dict(self):
        self.body = fedora_vm_body(name=self.name)
        res = super().to_dict()
        vm_interfaces = res["spec"]["template"]["spec"]["domain"]["devices"][
            "interfaces"
        ]
        for iface in vm_interfaces:
            if "masquerade" in iface.keys():
                iface["ports"] = [{"name": "http80", "port": 80, "protocol": "TCP"}]

        res["spec"]["template"]["metadata"]["labels"].update(
            {"kubevirt.io/domain": self.name}
        )

        return res


@pytest.fixture(scope="module")
def vma(namespace, unprivileged_client):
    networks = {BR1TEST: BR1TEST}
    network_data_data = {"ethernets": {"eth1": {"addresses": ["10.200.0.1/24"]}}}
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data.update(cloud_init_network_data(data=network_data_data))

    with BridgedFedoraVirtualMachine(
        namespace=namespace.name,
        name="vma",
        networks=networks,
        interfaces=sorted(networks.keys()),
        client=unprivileged_client,
        cloud_init_data=cloud_init_data,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def vmb(namespace, unprivileged_client):
    networks = {BR1TEST: BR1TEST}
    network_data_data = {"ethernets": {"eth1": {"addresses": ["10.200.0.2/24"]}}}
    cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
    cloud_init_data.update(cloud_init_network_data(data=network_data_data))

    with BridgedFedoraVirtualMachine(
        namespace=namespace.name,
        name="vmb",
        networks=networks,
        interfaces=sorted(networks.keys()),
        client=unprivileged_client,
        cloud_init_data=cloud_init_data,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def running_vma(vma):
    vmi = vma.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    enable_ssh_service_in_vm(vm=vma, console_impl=console.Fedora)
    yield vma


@pytest.fixture(scope="module")
def running_vmb(vmb):
    vmi = vmb.vmi
    vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmi)
    enable_ssh_service_in_vm(vm=vmb, console_impl=console.Fedora)
    yield vmb


@pytest.fixture(scope="module", autouse=True)
def bridge_on_all_nodes(
    skip_if_no_multinic_nodes,
    utility_pods,
    nodes_available_nics,
    schedulable_nodes,
):
    with network_utils.network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="migration",
        interface_name=BR1TEST,
        network_utility_pods=utility_pods,
        nodes=schedulable_nodes,
        ports=[get_hosts_common_ports(nodes_available_nics=nodes_available_nics)[1]],
    ) as br:
        yield br


@pytest.fixture(scope="module", autouse=True)
def br1test_nad(namespace):
    with network_nad(
        nad_type=LINUX_BRIDGE,
        nad_name=BR1TEST,
        interface_name=BR1TEST,
        namespace=namespace,
    ) as nad:
        yield nad


@pytest.fixture()
def http_service(namespace, running_vma, running_vmb):
    running_vmb.custom_service_enable(service_name="http-masquerade-migration", port=80)

    # Check that http service on port 80 can be accessed by cluster IP
    # before vmi migration.
    http_port_accessible(
        vm=running_vma,
        server_ip=running_vmb.custom_service_ip,
        server_port=running_vmb.custom_service_port,
    )


@pytest.fixture()
def ping_in_background(running_vma, running_vmb):
    dst_ip = get_vmi_ip_v4_by_name(vmi=running_vmb.vmi, name=BR1TEST)
    LOGGER.info(f"Ping {dst_ip} from {running_vma.name} to {running_vmb.name}")
    with console.Fedora(vm=running_vma) as vmc:
        vmc.sendline(f"sudo ping -i 0.1 {dst_ip} > /tmp/ping.log &")
        vmc.expect(r"\[\d+\].*\d+", timeout=10)
        vmc.sendline("echo $! > /tmp/ping.pid")


def assert_low_packet_loss(vm):
    with console.Fedora(vm=vm) as vmc:
        vmc.sendline("sudo kill -SIGINT `cat /tmp/ping.pid`")
        vmc.sendline("grep 'transmitted' /tmp/ping.log")
        vmc.expect("packet loss", 10)
        packet_loss = float(str(vmc.before).split()[-2].strip("%"))
        LOGGER.info(f"Packet loss percentage {packet_loss}")
        assert packet_loss < 4.0


@pytest.fixture()
def ssh_in_background(running_vma, running_vmb):
    """
    Start ssh connection to the vm
    """
    dst_ip = get_vmi_ip_v4_by_name(vmi=running_vmb.vmi, name=BR1TEST)
    LOGGER.info(f"Start ssh connection to {running_vmb.name} from {running_vma.name}")
    with console.Fedora(vm=running_vma) as vm_console:
        vm_console.sendline(
            f"sshpass -p fedora ssh -o 'StrictHostKeyChecking no' fedora@{dst_ip} 'sleep 99999'&"
        )
        vm_console.expect(r"\[\d+\].*\d+", timeout=10)
        vm_console.sendline("ps aux | grep 'sleep'")
        vm_console.expect("sshpass -p zzzzzz", timeout=10)


def assert_ssh_alive(ssh_vm):
    """
    Check the ssh process is alive
    """
    with console.Fedora(vm=ssh_vm) as tcp_vm_console:
        tcp_vm_console.sendline("ps aux | grep 'sleep'")
        tcp_vm_console.expect("sshpass -p zzzzzz", timeout=10)


@pytest.mark.polarion("CNV-2060")
def test_ping_vm_migration(
    skip_rhel7_workers,
    skip_when_one_node,
    vma,
    vmb,
    running_vma,
    running_vmb,
    ping_in_background,
):
    src_node = running_vmb.vmi.instance.status.nodeName
    with VirtualMachineInstanceMigration(
        name="l2-migration", namespace=running_vmb.namespace, vmi=running_vmb.vmi
    ) as mig:
        mig.wait_for_status(status=mig.Status.SUCCEEDED, timeout=720)
        assert running_vmb.vmi.instance.status.nodeName != src_node

    assert_low_packet_loss(vm=running_vma)


@pytest.mark.polarion("CNV-2063")
def test_ssh_vm_migration(
    skip_rhel7_workers,
    skip_when_one_node,
    namespace,
    vma,
    vmb,
    running_vma,
    running_vmb,
    ssh_in_background,
):
    src_node = running_vmb.vmi.instance.status.nodeName
    with VirtualMachineInstanceMigration(
        name="tcp-migration", namespace=namespace.name, vmi=running_vmb.vmi
    ) as mig:
        mig.wait_for_status(status=mig.Status.SUCCEEDED, timeout=720)
        assert running_vmb.vmi.instance.status.nodeName != src_node

    assert_ssh_alive(ssh_vm=running_vma)


@pytest.mark.polarion("CNV-2061")
def test_migration_with_masquerade(
    admin_client,
    skip_rhel7_workers,
    skip_when_one_node,
    utility_pods,
    vma,
    vmb,
    running_vma,
    running_vmb,
    http_service,
):
    vmi_node_before_migration = running_vmb.vmi.instance.status.nodeName
    with VirtualMachineInstanceMigration(
        name="masquerade-migration",
        namespace=running_vmb.namespace,
        vmi=running_vmb.vmi,
    ) as mig:
        mig.wait_for_status(status=mig.Status.SUCCEEDED, timeout=720)
        assert running_vmb.vmi.instance.status.nodeName != vmi_node_before_migration
        assert running_vmb.vmi.instance.status.migrationState.completed
        http_port_accessible(
            vm=running_vma,
            server_ip=running_vmb.custom_service_ip,
            server_port=running_vmb.custom_service_port,
        )
