import logging
from collections import OrderedDict

import pytest

from tests.network.utils import assert_ssh_alive, run_ssh_in_background
from utilities.infra import get_pod_by_name_prefix, name_prefix
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
BRIDGE_NAME = "br1test"


def restart_nmstate_handler(admin_client, hco_namespace, nmstate_ds):
    LOGGER.info("Delete NMstate PODs")
    for pod in get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix="nmstate-handler",
        namespace=hco_namespace.name,
        get_all=True,
    ):
        pod.delete(wait=True)
    nmstate_ds.wait_until_deployed()


@pytest.fixture(scope="class")
def nmstate_linux_bridge_device_worker_1(
    skip_if_no_multinic_nodes, nodes_available_nics, utility_pods, worker_node1
):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"restart-nmstate-{name_prefix(worker_node1.name)}",
        interface_name=BRIDGE_NAME,
        network_utility_pods=utility_pods,
        node_selector=worker_node1.hostname,
        ports=[nodes_available_nics[worker_node1.name][0]],
    ) as br_dev:
        yield br_dev


@pytest.fixture(scope="class")
def nmstate_linux_bridge_device_worker_2(
    skip_if_no_multinic_nodes, nodes_available_nics, utility_pods, worker_node2
):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"restart-nmstate-{name_prefix(worker_node2.name)}",
        interface_name=BRIDGE_NAME,
        network_utility_pods=utility_pods,
        node_selector=worker_node2.hostname,
        ports=[nodes_available_nics[worker_node2.name][0]],
    ) as br_dev:
        yield br_dev


@pytest.fixture(scope="class")
def nmstate_linux_nad(
    namespace,
    nmstate_linux_bridge_device_worker_1,
    nmstate_linux_bridge_device_worker_2,
):
    with network_nad(
        namespace=namespace,
        nad_type=nmstate_linux_bridge_device_worker_1.bridge_type,
        nad_name="nmstate-br1test-nad",
        interface_name=nmstate_linux_bridge_device_worker_1.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
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


@pytest.fixture(scope="class")
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


@pytest.fixture(scope="class")
def nmstate_linux_bridge_attached_running_vma(nmstate_linux_bridge_attached_vma):
    return running_vm(vm=nmstate_linux_bridge_attached_vma)


@pytest.fixture(scope="class")
def nmstate_linux_bridge_attached_running_vmb(nmstate_linux_bridge_attached_vmb):
    return running_vm(vm=nmstate_linux_bridge_attached_vmb)


@pytest.fixture(scope="class")
def vmb_dst_ip(nmstate_linux_nad, nmstate_linux_bridge_attached_running_vmb):
    return get_vmi_ip_v4_by_name(
        vm=nmstate_linux_bridge_attached_running_vmb,
        name=nmstate_linux_nad.name,
    )


@pytest.fixture(scope="class")
def vmb_pinged(vmb_dst_ip, nmstate_linux_bridge_attached_running_vma):
    assert_ping_successful(
        src_vm=nmstate_linux_bridge_attached_running_vma,
        dst_ip=vmb_dst_ip,
    )


@pytest.fixture(scope="class")
def ssh_in_vm_background(
    nmstate_linux_nad,
    nmstate_linux_bridge_attached_running_vma,
    nmstate_linux_bridge_attached_running_vmb,
):
    run_ssh_in_background(
        nad=nmstate_linux_nad,
        src_vm=nmstate_linux_bridge_attached_running_vma,
        dst_vm=nmstate_linux_bridge_attached_running_vmb,
        dst_vm_user=nmstate_linux_bridge_attached_running_vmb.username,
        dst_vm_password=nmstate_linux_bridge_attached_running_vmb.password,
    )


@pytest.fixture(scope="class")
def restarted_nmstate_handler(admin_client, hco_namespace, nmstate_ds):
    restart_nmstate_handler(
        admin_client=admin_client, hco_namespace=hco_namespace, nmstate_ds=nmstate_ds
    )


class TestNmstateHandlerRestart:
    @pytest.mark.post_upgrade
    @pytest.mark.polarion("CNV-5780")
    def test_nmstate_restart_and_check_connectivity(
        self,
        admin_client,
        hco_namespace,
        nmstate_ds,
        nmstate_linux_bridge_attached_vma,
        nmstate_linux_bridge_attached_vmb,
        nmstate_linux_bridge_attached_running_vma,
        nmstate_linux_bridge_attached_running_vmb,
        vmb_dst_ip,
        vmb_pinged,
    ):
        # Running 5 nmstate restarts since we saw some failures after few restarts.
        for idx in range(5):
            restart_nmstate_handler(
                admin_client=admin_client,
                hco_namespace=hco_namespace,
                nmstate_ds=nmstate_ds,
            )
            LOGGER.info(
                (
                    f"Check connectivity from {nmstate_linux_bridge_attached_running_vma.name} "
                    f"to {nmstate_linux_bridge_attached_running_vmb.name} "
                    f"IP {vmb_dst_ip}. NMstate restart number: {idx + 1}"
                )
            )

            assert_ping_successful(
                src_vm=nmstate_linux_bridge_attached_running_vma,
                dst_ip=vmb_dst_ip,
                count="60",
            )

    @pytest.mark.polarion("CNV-7746")
    def test_ssh_alive_after_restart_nmstate_handler(
        self,
        nmstate_linux_nad,
        nmstate_linux_bridge_attached_vma,
        nmstate_linux_bridge_attached_vmb,
        nmstate_linux_bridge_attached_running_vma,
        nmstate_linux_bridge_attached_running_vmb,
        ssh_in_vm_background,
        restarted_nmstate_handler,
    ):
        src_ip = str(
            get_vmi_ip_v4_by_name(
                vm=nmstate_linux_bridge_attached_vma, name=nmstate_linux_nad.name
            )
        )
        assert_ssh_alive(
            ssh_vm=nmstate_linux_bridge_attached_running_vma, src_ip=src_ip
        )
