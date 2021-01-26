"""
Connectivity over Linux_Bond on Default Interface
"""

import logging
import subprocess

import pytest
from resources.utils import TimeoutSampler

import tests.network.utils as network_utils
from utilities.network import BondNodeNetworkConfigurationPolicy, assert_ping_successful
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
def lbodi_vma(worker_node1, namespace, unprivileged_client):
    name = "vma"
    vm = VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=worker_node1.name,
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
    )
    vm.deploy()
    vm.start(wait=True)
    yield vm
    vm.clean_up()


@pytest.fixture(scope="class")
def lbodi_vmb(worker_node2, namespace, unprivileged_client):
    name = "vmb"
    vm = VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=worker_node2.name,
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
    )
    vm.deploy()
    vm.start(wait=True)
    yield vm
    vm.clean_up()


@pytest.fixture(scope="class")
def lbodi_running_vma(lbodi_vma):
    lbodi_vma.vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=lbodi_vma.vmi)
    return lbodi_vma


@pytest.fixture(scope="class")
def lbodi_running_vmb(lbodi_vmb):
    lbodi_vmb.vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=lbodi_vmb.vmi)
    return lbodi_vmb


@pytest.fixture(scope="class")
def lbodi_bond(
    index_number,
    skip_no_bond_support,
    utility_pods,
    nodes_available_nics,
    nodes_occupied_nics,
    worker_node1,
    worker_nodes_ipv4_false_secondary_nics,
):
    """
    Create BOND if setup support BOND
    """
    bond_idx = next(index_number)
    primary_slave = nodes_occupied_nics[worker_node1.name][0]
    bond = BondNodeNetworkConfigurationPolicy(
        name=f"bond{bond_idx}nncp",
        bond_name=f"bond{bond_idx}",
        slaves=[primary_slave, nodes_available_nics[worker_node1.name][0]],
        worker_pods=utility_pods,
        mode="active-backup",
        mtu=1450,
        node_selector=worker_node1.name,
        ipv4_dhcp=True,
        ipv4_enable=True,
        primary_slave=primary_slave,
    )
    bond.deploy()
    yield bond
    bond.clean_up()


@pytest.fixture(scope="class")
def lbodi_pod_with_bond(utility_pods, lbodi_bond):
    """
    Returns:
        The specific pod on the worker node with the bond
    """
    for pod in utility_pods:
        if pod.node.name == lbodi_bond.node_selector:
            return pod


@pytest.mark.destructive
class TestBondConnectivityWithNodesDefaultInterface:
    @pytest.mark.polarion("CNV-3432")
    def test_bond_config(
        self,
        skip_no_bond_support,
        namespace,
        lbodi_bond,
        lbodi_pod_with_bond,
    ):
        """
        Check that bond interface exists on the specific worker node,
        in Up state and has valid IP address.
        """
        bond_ip = network_utils.wait_for_address_on_iface(
            worker_pod=lbodi_pod_with_bond,
            iface_name=lbodi_bond.bond_name,
        )
        # Check connectivity
        assert subprocess.check_output(["ping", "-c", "1", bond_ip])

    @pytest.mark.polarion("CNV-3433")
    def test_vm_connectivity_over_linux_bond(
        self,
        skip_when_one_node,
        skip_no_bond_support,
        namespace,
        lbodi_bond,
        lbodi_vma,
        lbodi_vmb,
        lbodi_running_vma,
        lbodi_running_vmb,
    ):
        """
        Check connectivity from each VM
        to the default interface of the other VM.
        """
        vma_ip = lbodi_running_vma.vmi.virt_launcher_pod.instance.status.podIP
        vmb_ip = lbodi_running_vmb.vmi.virt_launcher_pod.instance.status.podIP
        for vm, ip in zip(
            [lbodi_running_vma, lbodi_running_vmb],
            [vmb_ip, vma_ip],
        ):
            assert_ping_successful(
                src_vm=vm,
                dst_ip=ip,
            )

    @pytest.mark.polarion("CNV-3439")
    def test_bond_and_persistence(
        self,
        skip_when_one_node,
        skip_no_bond_support,
        namespace,
        workers_ssh_executors,
        lbodi_bond,
        lbodi_pod_with_bond,
    ):
        """
        Verify bond interface status and persistence after reboot
        """
        worker_exec = workers_ssh_executors[lbodi_bond.node_selector]
        network_utils.wait_for_address_on_iface(
            worker_pod=lbodi_pod_with_bond,
            iface_name=lbodi_bond.bond_name,
        )

        # REBOOT - Check persistence
        worker_exec.executor().run_cmd(cmd=["bash", "-c", "sudo reboot"])
        LOGGER.info(f"Wait until {lbodi_bond.node_selector} reboots ...")
        samples = TimeoutSampler(
            timeout=TIMEOUT,
            sleep=SLEEP,
            func=worker_exec.executor().is_connective,
        )
        for sample in samples:
            if sample:
                break

        network_utils.wait_for_address_on_iface(
            worker_pod=lbodi_pod_with_bond,
            iface_name=lbodi_bond.bond_name,
        )
