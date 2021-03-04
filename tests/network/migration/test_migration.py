# -*- coding: utf-8 -*-
"""
Network Migration test
"""

import logging
import re
import shlex

import pytest
from ocp_resources.service import Service
from ocp_resources.utils import TimeoutSampler

from utilities.constants import IP_FAMILY_POLICY_PREFER_DUAL_STACK
from utilities.infra import run_ssh_commands
from utilities.network import (
    LINUX_BRIDGE,
    assert_ping_successful,
    compose_cloud_init_data_dict,
    get_ipv6_ip_str,
    get_vmi_ip_v4_by_name,
    network_device,
    network_nad,
)
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    migrate_and_verify,
    running_vm,
)


BR1TEST = "br1test"
PING_LOG = "ping.log"
LOGGER = logging.getLogger(__name__)


def http_port_accessible(vm, server_ip, server_port):
    if get_ipv6_ip_str(dst_ip=server_ip):
        server_ip = f"'[{server_ip}]'"

    sampler = TimeoutSampler(
        wait_timeout=120,
        sleep=5,
        func=run_ssh_commands,
        host=vm.ssh_exec,
        commands=[shlex.split(f"curl --head {server_ip}:{server_port}")],
    )
    for sample in sampler:
        if sample:
            return


@pytest.fixture(scope="module")
def vma(
    namespace,
    unprivileged_client,
    nodes_common_cpu_model,
    ipv6_network_data,
    bridge_worker_1,
):
    name = "vma"
    networks = {BR1TEST: BR1TEST}
    network_data_data = {"ethernets": {"eth1": {"addresses": ["10.200.0.1/24"]}}}
    cloud_init_data = compose_cloud_init_data_dict(
        network_data=network_data_data,
        ipv6_network_data=ipv6_network_data,
    )
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=sorted(networks.keys()),
        client=unprivileged_client,
        cloud_init_data=cloud_init_data,
        cpu_model=nodes_common_cpu_model,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def vmb(
    namespace,
    unprivileged_client,
    nodes_common_cpu_model,
    ipv6_network_data,
    bridge_worker_2,
):
    name = "vmb"
    networks = {BR1TEST: BR1TEST}
    network_data_data = {"ethernets": {"eth1": {"addresses": ["10.200.0.2/24"]}}}
    cloud_init_data = compose_cloud_init_data_dict(
        network_data=network_data_data,
        ipv6_network_data=ipv6_network_data,
    )

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=sorted(networks.keys()),
        client=unprivileged_client,
        cloud_init_data=cloud_init_data,
        cpu_model=nodes_common_cpu_model,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def running_vma(vma):
    return running_vm(vm=vma)


@pytest.fixture(scope="module")
def running_vmb(vmb):
    return running_vm(vm=vmb)


@pytest.fixture(scope="module")
def bridge_worker_1(
    skip_if_no_multinic_nodes,
    utility_pods,
    worker_node1,
    nodes_available_nics,
):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="migration-worker-1",
        interface_name=BR1TEST,
        network_utility_pods=utility_pods,
        node_selector=worker_node1.name,
        ports=[nodes_available_nics[worker_node1.name][0]],
    ) as br:
        yield br


@pytest.fixture(scope="module")
def bridge_worker_2(
    skip_if_no_multinic_nodes,
    utility_pods,
    worker_node2,
    nodes_available_nics,
):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="migration-worker-2",
        interface_name=BR1TEST,
        network_utility_pods=utility_pods,
        node_selector=worker_node2.name,
        ports=[nodes_available_nics[worker_node2.name][0]],
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
def restarted_vmb(running_vmb):
    running_vmb.restart(wait=True)
    return running_vm(vm=running_vmb, enable_ssh=False)


@pytest.fixture(scope="module")
def http_service(namespace, running_vma, running_vmb):
    running_vmb.custom_service_enable(
        service_name="http-masquerade-migration",
        port=80,
        service_type=Service.Type.CLUSTER_IP,
        ip_family_policy=IP_FAMILY_POLICY_PREFER_DUAL_STACK,
    )
    LOGGER.info(f"HTTP service was created on node {running_vmb.vmi.node.name}")

    # Check that http service on port 80 can be accessed by all cluster IPs
    # before vmi migration.
    for server_ip in running_vmb.custom_service.instance.spec.clusterIPs:
        http_port_accessible(
            vm=running_vma,
            server_ip=server_ip,
            server_port=running_vmb.custom_service.service_port,
        )


@pytest.fixture(scope="module")
def ping_in_background(running_vma, running_vmb):
    dst_ip = get_vmi_ip_v4_by_name(vmi=running_vmb.vmi, name=BR1TEST)
    assert_ping_successful(src_vm=running_vma, dst_ip=dst_ip)
    LOGGER.info(f"Ping {dst_ip} from {running_vma.name} to {running_vmb.name}")
    run_ssh_commands(
        host=running_vma.ssh_exec,
        commands=[shlex.split(f"sudo ping -i 0.1 {dst_ip} >& {PING_LOG} &")],
    )


def assert_low_packet_loss(vm):
    output = run_ssh_commands(
        host=vm.ssh_exec,
        commands=[
            shlex.split("sudo kill -SIGINT `pgrep ping`"),
            shlex.split(f"cat {PING_LOG}"),
        ],
    )
    packet_loss = re.findall(r"\d+.\d+% packet loss", output[1])
    assert packet_loss
    assert float(re.findall(r"\d+.\d+", packet_loss[0])[0]) < 2


@pytest.fixture(scope="module")
def ssh_in_background(running_vma, running_vmb):
    """
    Start ssh connection to the vm
    """
    dst_ip = get_vmi_ip_v4_by_name(vmi=running_vmb.vmi, name=BR1TEST)
    LOGGER.info(f"Start ssh connection to {running_vmb.name} from {running_vma.name}")
    run_ssh_commands(
        host=running_vma.ssh_exec,
        commands=[
            shlex.split(
                f"sshpass -p fedora ssh -o 'StrictHostKeyChecking no' fedora@{dst_ip} 'sleep 99999' &>1 &"
            )
        ],
    )

    assert_ssh_alive(ssh_vm=running_vma)


@pytest.fixture(scope="module")
def migrated_vmb(running_vmb, http_service):
    migrate_and_verify(
        vm=running_vmb,
        node_before=running_vmb.vmi.instance.status.nodeName,
    )


def assert_ssh_alive(ssh_vm):
    """
    Check the ssh process is alive
    """
    output = None
    sampler = TimeoutSampler(
        wait_timeout=30,
        sleep=1,
        func=run_ssh_commands,
        host=ssh_vm.ssh_exec,
        commands=[shlex.split("ps aux | grep 'sleep'")],
    )
    for sample in sampler:
        if sample:
            output = sample[0]
            break

    assert "sshpass -p zzzzzz" in output


@pytest.mark.polarion("CNV-2060")
def test_ping_vm_migration(
    skip_rhel7_workers,
    skip_when_one_node,
    vma,
    vmb,
    running_vma,
    running_vmb,
    ping_in_background,
    migrated_vmb,
):
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
    migrated_vmb,
):
    assert_ssh_alive(ssh_vm=running_vma)


@pytest.mark.polarion("CNV-5565")
def test_connectivity_after_migration_and_restart(
    skip_rhel7_workers,
    skip_when_one_node,
    namespace,
    vma,
    vmb,
    running_vma,
    running_vmb,
    restarted_vmb,
):
    assert_ping_successful(
        src_vm=running_vma,
        dst_ip=get_vmi_ip_v4_by_name(vmi=restarted_vmb.vmi, name=BR1TEST),
    )


@pytest.mark.polarion("CNV-2061")
def test_migration_with_masquerade(
    ip_stack_version_matrix__module__,
    admin_client,
    skip_rhel7_workers,
    skip_when_one_node,
    skip_ipv6_if_not_dual_stack_cluster,
    utility_pods,
    vma,
    vmb,
    running_vma,
    running_vmb,
    migrated_vmb,
):
    LOGGER.info(
        f"Testing HTTP service after migration on node {running_vmb.vmi.node.name}"
    )
    http_port_accessible(
        vm=running_vma,
        server_ip=running_vmb.custom_service.service_ip(
            ip_family=ip_stack_version_matrix__module__
        ),
        server_port=running_vmb.custom_service.service_port,
    )
