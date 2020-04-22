"""
Connectivity over Linux_Bond on Default Interface
"""

import logging
import subprocess

import pytest
import tests.network.utils as network_utils
from resources.utils import TimeoutExpiredError, TimeoutSampler
from rrmngmnt import power_manager
from utilities.network import BondNodeNetworkConfigurationPolicy
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


LOGGER = logging.getLogger(__name__)

TIMEOUT = 120
SLEEP = 15


def interface_status(worker_executor, nic_name):
    """
    Parameters:
        worker_executor (executor) - The specific executor
        nic_name (str)- The specific interface status checked

    Returns:
        If interface exists and in Up state - The interface's IP (str)
        Else - None
    """
    worker_network = worker_executor.network
    LOGGER.info(f"Wait until ip is assigned to interface - {nic_name}")
    if worker_network.get_interface_status(interface=nic_name) == "up":
        samples = TimeoutSampler(
            timeout=TIMEOUT,
            sleep=SLEEP,
            func=worker_network.find_ip_by_int,
            interface=nic_name,
        )
        try:
            for sample in samples:
                if sample:
                    return sample
        except TimeoutExpiredError:
            LOGGER.info(
                f"Timeout error while waiting for ip to be assigned to interface - {nic_name}"
            )
            return None


@pytest.fixture(scope="class")
def vma(schedulable_nodes, namespace, unprivileged_client):
    name = "vma"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=schedulable_nodes[0].name,
        client=unprivileged_client,
        body=fedora_vm_body(name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="class")
def vmb(schedulable_nodes, namespace, unprivileged_client):
    name = "vmb"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=schedulable_nodes[1].name,
        client=unprivileged_client,
        body=fedora_vm_body(name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="class")
def running_vma(vma):
    vma.vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vma.vmi)
    return vma


@pytest.fixture(scope="class")
def running_vmb(vmb):
    vmb.vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vmb.vmi)
    return vmb


@pytest.fixture(scope="class")
def bond(
    skip_no_bond_support, network_utility_pods, nodes_active_nics, schedulable_nodes,
):
    """
    Create BOND if setup support BOND
    """
    with BondNodeNetworkConfigurationPolicy(
        name="bond1nncp",
        bond_name="test-bond",
        slaves=nodes_active_nics[network_utility_pods[0].node.name][0:2],
        worker_pods=network_utility_pods,
        mode="active-backup",
        mtu=1450,
        node_selector=schedulable_nodes[0].name,
        ipv4_dhcp=True,
    ) as bond:
        yield bond


@pytest.mark.destructive
class TestBondConnectivityWithNodesDefaultInterface:
    @pytest.mark.polarion("CNV-3432")
    def test_bond_config(
        self,
        skip_no_bond_support,
        namespace,
        schedulable_node_ips,
        schedulable_nodes,
        workers_ssh_executors,
        bond,
    ):
        """
        Check that bond interface exists on the specific worker node,
        in Up state and has valid IP address.
        """
        interface_status_ip = interface_status(
            worker_executor=workers_ssh_executors[bond.node_selector],
            nic_name=bond.bond_name,
        )
        assert interface_status_ip
        # Check connectivity
        assert subprocess.check_output(["ping", "-c", "1", interface_status_ip])

    @pytest.mark.polarion("CNV-3433")
    def test_vm_connectivity_over_linux_bond(
        self,
        skip_when_one_node,
        skip_no_bond_support,
        namespace,
        bond,
        vma,
        vmb,
        running_vma,
        running_vmb,
    ):
        """
        Check connectivity from each VM
        to the default interface of the other VM.
        """
        vma_ip = running_vma.vmi.virt_launcher_pod.instance.status.podIP
        vmb_ip = running_vmb.vmi.virt_launcher_pod.instance.status.podIP
        for vm, ip in zip([running_vma, running_vmb], [vmb_ip, vma_ip]):
            network_utils.assert_ping_successful(
                src_vm=vm, dst_ip=ip,
            )

    @pytest.mark.polarion("CNV-3439")
    def test_bond_and_persistence(
        self,
        skip_when_one_node,
        skip_no_bond_support,
        namespace,
        nodes_active_nics,
        network_utility_pods,
        schedulable_nodes,
        workers_ssh_executors,
        bond,
    ):
        """
        Verify bond interface status and persistence after reboot
        """
        assert interface_status(
            worker_executor=workers_ssh_executors[bond.node_selector],
            nic_name=bond.bond_name,
        )
        host = workers_ssh_executors[bond.node_selector]
        host_executor = host.executor()
        host.add_power_manager(pm_type=power_manager.SSH_TYPE)
        pm = host.get_power_manager(pm_type=power_manager.SSH_TYPE)
        # REBOOT - Check persistence
        pm.restart()
        LOGGER.info(f"Wait until {bond.node_selector} reboots ...")
        samples = TimeoutSampler(
            timeout=TIMEOUT, sleep=SLEEP, func=host_executor.is_connective,
        )
        for sample in samples:
            if sample:
                assert interface_status(
                    worker_executor=workers_ssh_executors[bond.node_selector],
                    nic_name=bond.bond_name,
                )
                return
