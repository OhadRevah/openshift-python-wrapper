import logging
from collections import OrderedDict

import pytest
from pytest_testconfig import config as py_config
from resources.daemonset import DaemonSet

from utilities.infra import get_pod_by_name_prefix
from utilities.network import (
    LINUX_BRIDGE,
    assert_ping_successful,
    compose_cloud_init_data_dict,
    get_vmi_ip_v4_by_name,
    network_device,
    network_nad,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


LOGGER = logging.getLogger(__name__)
HCO_NAMESPACE = py_config["hco_namespace"]
BRIDGE_NAME = "br1test"


@pytest.fixture()
def nmstate_ds(admin_client):
    for ds in DaemonSet.get(
        dyn_client=admin_client, name="nmstate-handler", namespace=HCO_NAMESPACE
    ):
        return ds


@pytest.fixture()
def nmstate_linux_bridge_device_worker_1(
    nodes_available_nics, utility_pods, worker_node1
):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"restart-nmstate-{worker_node1.name}",
        interface_name=BRIDGE_NAME,
        network_utility_pods=utility_pods,
        node_selector=worker_node1.name,
        ports=[nodes_available_nics[worker_node1.name][0]],
    ) as br_dev:
        yield br_dev


@pytest.fixture()
def nmstate_linux_bridge_device_worker_2(
    nodes_available_nics, utility_pods, worker_node2
):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"restart-nmstate-{worker_node2.name}",
        interface_name=BRIDGE_NAME,
        network_utility_pods=utility_pods,
        node_selector=worker_node2.name,
        ports=[nodes_available_nics[worker_node2.name][0]],
    ) as br_dev:
        yield br_dev


@pytest.fixture()
def nmstate_linux_nad(
    namespace,
    nmstate_linux_bridge_device_worker_1,
    nmstate_linux_bridge_device_worker_2,
):
    with network_nad(
        namespace=namespace,
        nad_type=LINUX_BRIDGE,
        nad_name="nmstate-br1test-nad",
        interface_name=BRIDGE_NAME,
    ) as nad:
        yield nad


@pytest.fixture()
def nmstate_linux_bridge_attached_vma(
    worker_node1,
    namespace,
    unprivileged_client,
    nmstate_linux_nad,
):
    name = "vma"
    networks = OrderedDict()
    networks[nmstate_linux_nad.name] = nmstate_linux_nad.name
    network_data_data = {
        "ethernets": {
            "eth1": {"addresses": ["10.200.0.1/24"]},
        }
    }

    cloud_init_data = compose_cloud_init_data_dict(
        network_data=network_data_data,
    )

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=worker_node1.name,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture()
def nmstate_linux_bridge_attached_vmb(
    worker_node2,
    namespace,
    unprivileged_client,
    nmstate_linux_nad,
):
    name = "vmb"
    networks = OrderedDict()
    networks[nmstate_linux_nad.name] = nmstate_linux_nad.name
    network_data_data = {
        "ethernets": {
            "eth1": {"addresses": ["10.200.0.2/24"]},
        }
    }

    cloud_init_data = compose_cloud_init_data_dict(
        network_data=network_data_data,
    )

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=worker_node2.name,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture()
def nmstate_linux_bridge_attached_running_vma(nmstate_linux_bridge_attached_vma):
    return running_vm(vm=nmstate_linux_bridge_attached_vma)


@pytest.fixture()
def nmstate_linux_bridge_attached_running_vmb(nmstate_linux_bridge_attached_vmb):
    return running_vm(vm=nmstate_linux_bridge_attached_vmb)


@pytest.mark.polarion("CNV-5780")
def test_nmstate_restart_and_check_connectivity(
    admin_client,
    nmstate_ds,
    nmstate_linux_nad,
    nmstate_linux_bridge_attached_vma,
    nmstate_linux_bridge_attached_vmb,
    nmstate_linux_bridge_attached_running_vma,
    nmstate_linux_bridge_attached_running_vmb,
):
    dst_ip = get_vmi_ip_v4_by_name(
        vmi=nmstate_linux_bridge_attached_running_vmb.vmi,
        name=nmstate_linux_nad.name,
    )
    ping_log = (
        f"Check connectivity from {nmstate_linux_bridge_attached_running_vma.name} "
        f"to {nmstate_linux_bridge_attached_running_vmb.name} "
        f"IP {dst_ip}"
    )

    for idx in range(5):
        if idx == 0:
            LOGGER.info(f"{ping_log} Before NMstate redeployed")
            assert_ping_successful(
                src_vm=nmstate_linux_bridge_attached_running_vma,
                dst_ip=dst_ip,
            )
        nmstate_pods = get_pod_by_name_prefix(
            dyn_client=admin_client,
            pod_prefix="nmstate-handler",
            namespace=HCO_NAMESPACE,
            get_all=True,
        )
        LOGGER.info("Delete NMstate PODs")
        for pod in nmstate_pods:
            pod.delete(wait=True)

        nmstate_ds.wait_until_deployed()
        LOGGER.info(f"{ping_log} after NMstate PODs redeployed")

        LOGGER.info(f"Ping number: {idx}")
        assert_ping_successful(
            src_vm=nmstate_linux_bridge_attached_running_vma,
            dst_ip=dst_ip,
            count="60",
        )
