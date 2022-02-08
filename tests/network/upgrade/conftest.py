import shlex

import pytest
from ocp_resources.service_account import ServiceAccount

from tests.network.constants import (
    HTTPBIN_COMMAND,
    HTTPBIN_IMAGE,
    PORT_8080,
    SERVICE_MESH_PORT,
)
from tests.network.utils import (
    CirrosVirtualMachineForServiceMesh,
    ServiceMeshDeployments,
    ServiceMeshDeploymentService,
    ServiceMeshMemberRollForTests,
)
from utilities.network import LINUX_BRIDGE, cloud_init, network_nad
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


NAD_MAC_SPOOF_NAME = "brspoofupgrade"


@pytest.fixture(scope="session")
def upgrade_linux_macspoof_nad(
    upgrade_namespace_scope_session,
):
    with network_nad(
        namespace=upgrade_namespace_scope_session,
        nad_type=LINUX_BRIDGE,
        nad_name=NAD_MAC_SPOOF_NAME,
        interface_name=NAD_MAC_SPOOF_NAME,
        macspoofchk=True,
        add_resource_name=False,
    ) as nad:
        yield nad


@pytest.fixture(scope="session")
def vm_nad_networks_data(upgrade_linux_macspoof_nad):
    return {upgrade_linux_macspoof_nad.name: upgrade_linux_macspoof_nad.name}


@pytest.fixture(scope="session")
def vma_upgrade_mac_spoof(
    worker_node1, unprivileged_client, upgrade_linux_macspoof_nad, vm_nad_networks_data
):
    name = "vma-macspoof"
    with VirtualMachineForTests(
        name=name,
        namespace=upgrade_linux_macspoof_nad.namespace,
        networks=vm_nad_networks_data,
        interfaces=sorted(vm_nad_networks_data.keys()),
        client=unprivileged_client,
        cloud_init_data=cloud_init(ip_address="10.200.0.1"),
        body=fedora_vm_body(name=name),
        node_selector=worker_node1.hostname,
        running=True,
    ) as vm:
        yield vm


@pytest.fixture(scope="session")
def vmb_upgrade_mac_spoof(
    worker_node1, unprivileged_client, upgrade_linux_macspoof_nad, vm_nad_networks_data
):
    name = "vmb-macspoof"
    with VirtualMachineForTests(
        name=name,
        namespace=upgrade_linux_macspoof_nad.namespace,
        networks=vm_nad_networks_data,
        interfaces=sorted(vm_nad_networks_data.keys()),
        client=unprivileged_client,
        cloud_init_data=cloud_init(ip_address="10.200.0.2"),
        body=fedora_vm_body(name=name),
        node_selector=worker_node1.hostname,
        running=True,
    ) as vm:
        yield vm


@pytest.fixture(scope="session")
def running_vma_upgrade_mac_spoof(vma_upgrade_mac_spoof):
    return running_vm(vm=vma_upgrade_mac_spoof)


@pytest.fixture(scope="session")
def running_vmb_upgrade_mac_spoof(vmb_upgrade_mac_spoof):
    return running_vm(vm=vmb_upgrade_mac_spoof)


@pytest.fixture(scope="session")
def httpbin_service_mesh_deployment_for_upgrade(upgrade_namespace_scope_session):
    with ServiceMeshDeployments(
        name="httpbin",
        namespace=upgrade_namespace_scope_session.name,
        version=ServiceMeshDeployments.ApiVersion.V1,
        image=HTTPBIN_IMAGE,
        command=shlex.split(HTTPBIN_COMMAND),
        port=PORT_8080,
        service_port=SERVICE_MESH_PORT,
        service_account=True,
    ) as dp:
        yield dp


@pytest.fixture(scope="session")
def httpbin_service_mesh_service_account_for_upgrade(
    httpbin_service_mesh_deployment_for_upgrade,
):
    with ServiceAccount(
        name=httpbin_service_mesh_deployment_for_upgrade.app_name,
        namespace=httpbin_service_mesh_deployment_for_upgrade.namespace,
    ) as sa:
        yield sa


@pytest.fixture(scope="session")
def httpbin_service_mesh_service_for_upgrade(
    httpbin_service_mesh_deployment_for_upgrade,
    httpbin_service_mesh_service_account_for_upgrade,
):
    with ServiceMeshDeploymentService(
        namespace=httpbin_service_mesh_deployment_for_upgrade.namespace,
        app_name=httpbin_service_mesh_deployment_for_upgrade.app_name,
        port=httpbin_service_mesh_deployment_for_upgrade.service_port,
    ) as sv:
        yield sv


@pytest.fixture(scope="session")
def service_mesh_member_roll_for_upgrade(upgrade_namespace_scope_session):
    with ServiceMeshMemberRollForTests(
        members=[upgrade_namespace_scope_session.name]
    ) as smmr:
        yield smmr


@pytest.fixture(scope="session")
def vm_cirros_with_service_mesh_annotation_for_upgrade(
    unprivileged_client,
    upgrade_namespace_scope_session,
    service_mesh_member_roll_for_upgrade,
):
    vm_name = "service-mesh-vm"
    with CirrosVirtualMachineForServiceMesh(
        client=unprivileged_client,
        name=vm_name,
        namespace=upgrade_namespace_scope_session.name,
    ) as vm:
        vm.custom_service_enable(
            service_name=vm_name,
            port=SERVICE_MESH_PORT,
        )
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)
        yield vm
