"""
Connectivity over Linux_Bond on Default Interface
"""

import logging
import subprocess

import pytest
import tests.network.utils as network_utils
from resources.utils import TimeoutSampler
from utilities.network import BondNodeNetworkConfigurationPolicy
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


LOGGER = logging.getLogger(__name__)
TIMEOUT = 600
SLEEP = 5


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


@pytest.fixture(scope="class")
def get_pod_with_bond(network_utility_pods, bond):
    """
    Returns:
        The specific pod on the worker node with the bond
    """
    for pod in network_utility_pods:
        if pod.node.name == bond.node_selector:
            return pod


@pytest.mark.destructive
class TestBondConnectivityWithNodesDefaultInterface:
    @pytest.mark.polarion("CNV-3432")
    def test_bond_config(
        self, skip_no_bond_support, namespace, bond, get_pod_with_bond,
    ):
        """
        Check that bond interface exists on the specific worker node,
        in Up state and has valid IP address.
        """
        bond_ip = network_utils.wait_for_address_on_iface(
            worker_pod=get_pod_with_bond, iface_name=bond.bond_name,
        )
        # Check connectivity
        assert subprocess.check_output(["ping", "-c", "1", bond_ip])

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
        workers_ssh_executors,
        bond,
        get_pod_with_bond,
    ):
        """
        Verify bond interface status and persistence after reboot
        """
        worker_exec = workers_ssh_executors[bond.node_selector]
        network_utils.wait_for_address_on_iface(
            worker_pod=get_pod_with_bond, iface_name=bond.bond_name,
        )

        # REBOOT - Check persistence
        worker_exec.executor().run_cmd(cmd=["bash", "-c", "sudo reboot"])
        LOGGER.info(f"Wait until {bond.node_selector} reboots ...")
        samples = TimeoutSampler(
            timeout=TIMEOUT, sleep=SLEEP, func=worker_exec.executor().is_connective,
        )
        for sample in samples:
            if sample:
                break

        network_utils.wait_for_address_on_iface(
            worker_pod=get_pod_with_bond, iface_name=bond.bond_name,
        )
