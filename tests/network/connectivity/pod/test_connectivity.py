"""
VM to VM connectivity
"""
from ipaddress import ip_interface

import pytest
from pytest_testconfig import config as py_config

from resources.namespace import Namespace
from tests.network.connectivity import utils
from tests.network.utils import run_test_connectivity
from tests.utils import wait_for_vm_interfaces, FedoraVirtualMachine


class FedoraVirtualMachineTest(FedoraVirtualMachine):
    def __init__(
        self,
        name,
        namespace,
        client=None,
        interfaces=None,
        networks=None,
        node_selector=None,
    ):
        super().__init__(
            name=name,
            namespace=namespace,
            client=client,
            interfaces=interfaces,
            networks=networks,
            node_selector=node_selector,
        )


@pytest.fixture(scope="module", autouse=True)
def module_namespace():
    with Namespace(name="pod-connectivity") as ns:
        yield ns


@pytest.fixture(scope="module")
def vma(module_namespace, network_utility_pods):
    with FedoraVirtualMachineTest(
        namespace=module_namespace.name,
        name="vma",
        node_selector=network_utility_pods[0].node.name,
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture(scope="module")
def vmb(module_namespace, network_utility_pods):
    with FedoraVirtualMachineTest(
        namespace=module_namespace.name,
        name="vmb",
        node_selector=network_utility_pods[1].node.name,
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture(scope="module")
def running_vma(vma):
    assert wait_for_vm_interfaces(vmi=vma.vmi)
    return vma


@pytest.fixture(scope="module")
def running_vmb(vmb):
    assert wait_for_vm_interfaces(vmi=vmb.vmi)
    return vmb


@pytest.mark.polarion("CNV-2332")
def test_connectivity_over_pod_network(
    skip_when_one_node, vma, vmb, running_vma, running_vmb, module_namespace
):
    """
    Check connectivity
    """
    run_test_connectivity(
        src_vm=running_vma,
        dst_ip=ip_interface(running_vma.vmi.interfaces[0]["ipAddress"]).ip,
        positive=True,
    )


@pytest.mark.skipif(not py_config["bare_metal_cluster"], reason="virtualized cluster")
@pytest.mark.xfail(reason="Slow performance on BM, need investigation")
@pytest.mark.polarion("CNV-2334")
def test_guest_performance_over_pod_network(
    skip_when_one_node, vma, vmb, running_vma, running_vmb, module_namespace
):
    """
    In-guest performance bandwidth passthrough over Linux bridge
    """
    expected_res = py_config["test_guest_performance"]["bandwidth"]
    bits_per_second = utils.run_test_guest_performance(
        server_vm=running_vma.name,
        client_vm=running_vmb.name,
        listen_ip=ip_interface(running_vma.vmi.interfaces[0]["ipAddress"]).ip,
        namespace=module_namespace.name,
    )
    assert bits_per_second >= expected_res
