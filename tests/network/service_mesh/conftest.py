import logging
import shlex
import time

import pytest
from ocp_resources.destination_rule import DestinationRule
from ocp_resources.gateway import Gateway
from ocp_resources.namespace import Namespace
from ocp_resources.peer_authentication import PeerAuthentication
from ocp_resources.resource import ResourceEditor
from ocp_resources.service import Service
from ocp_resources.service_account import ServiceAccount
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from ocp_resources.virtual_service import VirtualService

from tests.network.constants import (
    HTTPBIN_COMMAND,
    HTTPBIN_IMAGE,
    PORT_8080,
    SERVICE_MESH_PORT,
)
from tests.network.service_mesh.constants import (
    DESTINATION_RULE_TYPE,
    GATEWAY_SELECTOR,
    GATEWAY_TYPE,
    HTTP_PROTOCOL,
    INGRESS_SERVICE,
    PEER_AUTHENTICATION_TYPE,
    PORT_80,
    SERVER_DEMO_HOST,
    SERVER_DEMO_NAME,
    SERVER_DEPLOYMENT_STRATEGY,
    SERVER_V1_IMAGE,
    SERVER_V2_IMAGE,
    VERSION_2_DEPLOYMENT,
    VIRTUAL_SERVICE_TYPE,
)
from tests.network.service_mesh.utils import traffic_management_request
from tests.network.utils import (
    CirrosVirtualMachineForServiceMesh,
    ServiceMeshDeployments,
    ServiceMeshDeploymentService,
    ServiceMeshMemberRollForTests,
    authentication_request,
)
from utilities.constants import ISTIO_SYSTEM_DEFAULT_NS, TIMEOUT_2MIN
from utilities.infra import create_ns, run_ssh_commands
from utilities.virt import running_vm


LOGGER = logging.getLogger(__name__)


def unique_name(name, type):
    # Sets Service unique name - replaces "." with "-" in the name to handle valid values.
    return f"{name}-{type}-{time.time()}".replace(".", "-")


class GatewayForTests(Gateway):
    def __init__(self, app_name, namespace, hosts):
        self.name = unique_name(name=app_name, type=GATEWAY_TYPE)
        super().__init__(
            name=self.name,
            namespace=namespace,
        )
        self.hosts = hosts

    def to_dict(self):
        res = super().to_dict()
        res.setdefault("spec", {})
        res["spec"]["selector"] = GATEWAY_SELECTOR
        res["spec"]["servers"] = [
            {
                "port": {
                    "number": PORT_80,
                    "name": HTTP_PROTOCOL.lower(),
                    "protocol": HTTP_PROTOCOL,
                },
                "hosts": self.hosts,
            }
        ]
        return res


class DestinationRuleForTests(DestinationRule):
    def __init__(self, app_name, namespace, versions):
        self.name = unique_name(name=app_name, type=DESTINATION_RULE_TYPE)
        super().__init__(
            name=self.name,
            namespace=namespace,
        )
        self.app_name = app_name
        self.versions = versions

    def to_dict(self):
        res = super().to_dict()
        res.setdefault("spec", {})
        res["spec"]["host"] = self.app_name
        res["spec"].setdefault("subsets", [])
        for version in self.versions:
            res["spec"]["subsets"].append(
                {
                    "name": version,  # Same as inner name.
                    "labels": {
                        "version": version  # Maps to version label in deployment
                    },
                }
            )
        return res


class VirtualServiceForTests(VirtualService):
    def __init__(
        self,
        app_name,
        namespace,
        hosts,
        gateways,
        subset,
        port,
    ):
        self.name = unique_name(name=app_name, type=VIRTUAL_SERVICE_TYPE)
        super().__init__(
            name=self.name,
            namespace=namespace,
        )
        self.hosts = hosts
        self.gateways = gateways
        self.subset = subset
        self.port = port
        self.app_name = app_name

    def to_dict(self):
        res = super().to_dict()
        res.setdefault("spec", {})
        res["spec"]["hosts"] = self.hosts
        res["spec"]["gateways"] = self.gateways
        res["spec"]["http"] = [
            {
                "match": [
                    {
                        "uri": {
                            "prefix": "/",
                        },
                    },
                ],
                "route": [
                    {
                        "destination": {
                            "port": {"number": self.port},
                            "host": self.app_name,
                            "subset": self.subset,  # Map to the name in DestinationRule
                        },
                    },
                ],
            },
        ]
        return res


class PeerAuthenticationForTests(PeerAuthentication):
    def __init__(self, name, namespace):
        self.name = unique_name(name=name, type=PEER_AUTHENTICATION_TYPE)
        super().__init__(
            name=self.name,
            namespace=namespace,
        )

    def to_dict(self):
        res = super().to_dict()
        res["spec"] = {"mtls": {"mode": PeerAuthentication.MtlsMode.STRICT}}
        return res


def wait_service_mesh_components_convergence(func, vm, **kwargs):
    server_response = None
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_2MIN,
            sleep=5,
            func=func,
            vm=vm,
            **kwargs,
        ):
            server_response = sample[0]
            if "no healthy upstream" not in server_response:
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"Service Mesh components didn't converge. Server response - {server_response}"
        )
        raise


@pytest.fixture(scope="module")
def skip_if_service_mesh_not_installed(istio_system_namespace):
    # Service mesh not installed if the cluster doesn't have ISTIO-SYSTEM ns
    if not istio_system_namespace:
        pytest.skip(msg="Cannot run the test. Service Mesh not installed")


@pytest.fixture(scope="module")
def istio_system_namespace(admin_client):
    return Namespace(name=ISTIO_SYSTEM_DEFAULT_NS, client=admin_client).exists


@pytest.fixture(scope="module")
def ns_outside_of_service_mesh(admin_client):
    yield from create_ns(admin_client=admin_client, name="outside-mesh")


@pytest.fixture(scope="class")
def httpbin_deployment_service_mesh(namespace):
    with ServiceMeshDeployments(
        name="httpbin",
        namespace=namespace.name,
        version=ServiceMeshDeployments.ApiVersion.V1,
        image=HTTPBIN_IMAGE,
        command=shlex.split(HTTPBIN_COMMAND),
        port=PORT_8080,
        service_port=SERVICE_MESH_PORT,
        service_account=True,
    ) as dp:
        yield dp


@pytest.fixture(scope="class")
def httpbin_service_account_service_mesh(httpbin_deployment_service_mesh):
    with ServiceAccount(
        name=httpbin_deployment_service_mesh.app_name,
        namespace=httpbin_deployment_service_mesh.namespace,
    ) as sa:
        yield sa


@pytest.fixture(scope="class")
def httpbin_service_service_mesh(
    httpbin_deployment_service_mesh, httpbin_service_account_service_mesh
):
    with ServiceMeshDeploymentService(
        namespace=httpbin_deployment_service_mesh.namespace,
        app_name=httpbin_deployment_service_mesh.app_name,
        port=httpbin_deployment_service_mesh.service_port,
    ) as sv:
        yield sv


@pytest.fixture(scope="module")
def service_mesh_member_roll(namespace):
    with ServiceMeshMemberRollForTests(members=[namespace.name]) as smmr:
        yield smmr


@pytest.fixture(scope="module")
def vm_cirros_with_service_mesh_annotation(
    unprivileged_client,
    namespace,
    service_mesh_member_roll,
):
    vm_name = "service-mesh-vm"
    with CirrosVirtualMachineForServiceMesh(
        client=unprivileged_client,
        name=vm_name,
        namespace=namespace.name,
    ) as vm:
        vm.custom_service_enable(
            service_name=vm_name,
            port=SERVICE_MESH_PORT,
        )
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)
        yield vm


@pytest.fixture(scope="module")
def outside_mesh_vm_cirros_with_service_mesh_annotation(
    admin_client,
    ns_outside_of_service_mesh,
):
    vm_name = "out-service-mesh-vm"
    with CirrosVirtualMachineForServiceMesh(
        client=admin_client,
        name=vm_name,
        namespace=ns_outside_of_service_mesh.name,
    ) as vm:
        vm.custom_service_enable(
            service_name=vm_name,
            port=SERVICE_MESH_PORT,
        )
        running_vm(vm=vm, wait_for_interfaces=False)
        yield vm


@pytest.fixture(scope="class")
def server_deployment_v1(namespace):
    with ServiceMeshDeployments(
        name=SERVER_DEMO_NAME,
        namespace=namespace.name,
        version=ServiceMeshDeployments.ApiVersion.V1,
        image=SERVER_V1_IMAGE,
        strategy=SERVER_DEPLOYMENT_STRATEGY,
        host=SERVER_DEMO_HOST,
        service_port=PORT_8080,
    ) as dp:
        yield dp


@pytest.fixture(scope="class")
def server_deployment_v2(server_deployment_v1):
    with ServiceMeshDeployments(
        name=server_deployment_v1.app_name,
        namespace=server_deployment_v1.namespace,
        version=VERSION_2_DEPLOYMENT,
        image=SERVER_V2_IMAGE,
        strategy=server_deployment_v1.strategy,
        host=server_deployment_v1.host,
        service_port=server_deployment_v1.service_port,
    ) as dp:
        yield dp


@pytest.fixture(scope="class")
def server_service_service_mesh(server_deployment_v1):
    with ServiceMeshDeploymentService(
        app_name=server_deployment_v1.app_name,
        namespace=server_deployment_v1.namespace,
        port=server_deployment_v1.service_port,
    ) as sv:
        yield sv


@pytest.fixture(scope="class")
def gateway_service_mesh(server_deployment_v1):
    with GatewayForTests(
        app_name=server_deployment_v1.app_name,
        namespace=server_deployment_v1.namespace,
        hosts=[server_deployment_v1.host],
    ) as gw:
        yield gw


@pytest.fixture(scope="class")
def virtual_service_mesh_service(server_deployment_v1, gateway_service_mesh):
    with VirtualServiceForTests(
        app_name=server_deployment_v1.app_name,
        namespace=server_deployment_v1.namespace,
        hosts=[server_deployment_v1.host],
        gateways=[gateway_service_mesh.name],
        subset=server_deployment_v1.version,
        port=server_deployment_v1.service_port,
    ) as vsv:
        yield vsv


@pytest.fixture(scope="class")
def destination_rule_service_mesh(server_deployment_v1, server_deployment_v2):
    with DestinationRuleForTests(
        app_name=server_deployment_v1.app_name,
        namespace=server_deployment_v1.namespace,
        versions=[server_deployment_v1.version, server_deployment_v2.version],
    ) as dr:
        yield dr


@pytest.fixture(scope="class")
def traffic_management_service_mesh_convergence(
    istio_system_namespace,
    vm_cirros_with_service_mesh_annotation,
    server_deployment_v1,
    server_deployment_v2,
    server_service_service_mesh,
    gateway_service_mesh,
    destination_rule_service_mesh,
    virtual_service_mesh_service,
    service_mesh_ingress_service_addr,
):
    wait_service_mesh_components_convergence(
        func=traffic_management_request,
        vm=vm_cirros_with_service_mesh_annotation,
        server=server_deployment_v1,
        destination=service_mesh_ingress_service_addr,
    )


@pytest.fixture(scope="class")
def service_mesh_ingress_service_addr(admin_client, istio_system_namespace):
    for svc in Service.get(
        dyn_client=admin_client,
        name=INGRESS_SERVICE,
        namespace=istio_system_namespace.metadata.name,
    ):
        return svc.instance.spec.clusterIP


@pytest.fixture()
def change_routing_to_v2(
    virtual_service_mesh_service,
    server_deployment_v2,
    vm_cirros_with_service_mesh_annotation,
    service_mesh_ingress_service_addr,
):
    LOGGER.info(
        f"Change routing to direct traffic only to: {server_deployment_v2.version}"
    )
    patch = {
        "spec": {
            "http": [
                {
                    "route": [
                        {
                            "destination": {
                                "port": {"number": server_deployment_v2.service_port},
                                "host": server_deployment_v2.app_name,
                                "subset": server_deployment_v2.version,  # Map to the name in DestinationRule
                            },
                        },
                    ],
                },
            ]
        }
    }
    ResourceEditor(patches={virtual_service_mesh_service: patch}).update()
    wait_service_mesh_components_convergence(
        func=traffic_management_request,
        vm=vm_cirros_with_service_mesh_annotation,
        server=server_deployment_v2,
        destination=service_mesh_ingress_service_addr,
    )


@pytest.fixture(scope="class")
def peer_authentication_strict_service_mesh(service_mesh_member_roll, namespace):
    with PeerAuthenticationForTests(
        name=service_mesh_member_roll.name, namespace=namespace.name
    ) as pa:
        yield pa


@pytest.fixture(scope="class")
def peer_authentication_service_mesh_deployment(
    istio_system_namespace,
    namespace,
    service_mesh_member_roll,
    vm_cirros_with_service_mesh_annotation,
    ns_outside_of_service_mesh,
    httpbin_service_service_mesh,
    peer_authentication_strict_service_mesh,
):
    wait_service_mesh_components_convergence(
        func=authentication_request,
        vm=vm_cirros_with_service_mesh_annotation,
        service=httpbin_service_service_mesh.app_name,
    )


@pytest.fixture()
def vmi_http_server(vm_cirros_with_service_mesh_annotation):
    run_ssh_commands(
        host=vm_cirros_with_service_mesh_annotation.ssh_exec,
        commands=shlex.split(
            f'while true ; do  echo -e "HTTP/1.1 200 OK\n\n $(date)" | nc -l -p {SERVICE_MESH_PORT}  ; done &'
        ),
    )
