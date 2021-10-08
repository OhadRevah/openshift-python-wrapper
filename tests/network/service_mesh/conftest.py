import logging
import time

import pytest
from ocp_resources.deployment import Deployment
from ocp_resources.destination_rule import DestinationRule
from ocp_resources.gateway import Gateway
from ocp_resources.namespace import Namespace
from ocp_resources.peer_authentication import PeerAuthentication
from ocp_resources.resource import ResourceEditor
from ocp_resources.service import Service
from ocp_resources.service_mesh_member_roll import ServiceMeshMemberRoll
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from ocp_resources.virtual_service import VirtualService

from tests.network.service_mesh.constants import (
    CIRROS_IMAGE,
    DEPLOYMENT_TYPE,
    DESTINATION_RULE_TYPE,
    GATEWAY_SELECTOR,
    GATEWAY_TYPE,
    HTTP_PROTOCOL,
    INGRESS_SERVICE,
    ISTIO_SYSTEM_DEFAULT_NS,
    PEER_AUTHENTICATION_TYPE,
    PORT_80,
    PORT_8080,
    SERVER_DEMO_HOST,
    SERVER_DEMO_NAME,
    SERVER_DEPLOYMENT_STRATEGY,
    SERVER_V1_IMAGE,
    SERVER_V2_IMAGE,
    SM_INJECT_ANNOTATION,
    SM_PORT,
    SM_VM_MEMORY_REQ,
    SMMR_NAME,
    SSH_PORT,
    VERSION_1_DEPLOYMENT,
    VERSION_2_DEPLOYMENT,
    VIRTUAL_SERVICE_TYPE,
)
from tests.network.service_mesh.utils import traffic_management_request
from utilities.constants import OS_FLAVOR_CIRROS, TIMEOUT_1MIN
from utilities.virt import VirtualMachineForTests, running_vm


LOGGER = logging.getLogger(__name__)


def unique_name(name, type):
    # Sets Service unique name - replaces "." with "-" in the name to handle valid values.
    return f"{name}-{type}-{time.time()}".replace(".", "-")


class CirrosVirtualMachinefForServiceMesh(VirtualMachineForTests):
    def __init__(
        self,
        name,
        namespace,
        client,
        interface_port=SM_PORT,
    ):
        """
        Cirros VM Creation

        Special Args:
            interface_port: Should be any port different from istio-used ports
        """
        super().__init__(
            name=name,
            namespace=namespace,
            client=client,
            os_flavor=OS_FLAVOR_CIRROS,
            memory_requests=SM_VM_MEMORY_REQ,
            image=CIRROS_IMAGE,
        )
        self.interface_port = interface_port

    def to_dict(self):
        res = super().to_dict()
        res["spec"]["template"]["metadata"].setdefault("annotations", {})
        res["spec"]["template"]["metadata"]["annotations"] = {
            SM_INJECT_ANNOTATION: "true",
        }
        res["spec"]["template"]["spec"]["domain"]["devices"]["interfaces"] = [
            {
                "name": "default",
                "masquerade": {},
                "ports": [
                    {
                        "port": self.interface_port,
                    },
                    {"port": SSH_PORT},
                ],
            }
        ]
        res["spec"]["template"]["spec"]["networks"] = [{"name": "default", "pod": {}}]

        return res


class SMDeploymentService(Service):
    def __init__(self, app_name, namespace, port, port_name=None):
        super().__init__(
            name=app_name,
            namespace=namespace,
        )
        self.port = port
        self.app_name = app_name
        self.port_name = port_name

    def to_dict(self):
        res = super().to_dict()
        res.setdefault("spec", {})
        res["spec"]["selector"] = {"app": self.app_name}
        res["spec"]["ports"] = [
            {
                "port": self.port,
                "protocol": "TCP",
            },
        ]
        if self.port_name:
            res["spec"]["ports"][0]["name"] = self.port_name
        return res


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
    def __init__(
        self,
        name,
    ):
        self.name = unique_name(name=name, type=PEER_AUTHENTICATION_TYPE)
        super().__init__(
            name=self.name,
            namespace=ISTIO_SYSTEM_DEFAULT_NS,
        )

    def to_dict(self):
        res = super().to_dict()
        res["spec"] = {"mtls": {"mode": PeerAuthentication.MtlsMode.STRICT}}
        return res


class ServiceMeshDeployments(Deployment):
    def __init__(
        self,
        name,
        namespace,
        version,
        image,
        replicas=1,
        command=None,
        strategy=None,
        service_account=False,
        policy="Always",
        service_port=None,
        host=None,
        port=None,
    ):
        self.name = unique_name(name=f"{name}-{version}", type=DEPLOYMENT_TYPE)
        super().__init__(name=self.name, namespace=namespace)
        self.version = version
        self.replicas = replicas
        self.image = image
        self.strategy = strategy
        self.service_account = service_account
        self.policy = policy
        self.port = port
        self.app_name = name
        self.command = command
        self.service_port = service_port
        self.host = host

    def to_dict(self):
        res = super().to_dict()
        res.setdefault("spec", {})
        res["spec"]["replicas"] = self.replicas
        res["spec"]["selector"] = {
            "matchLabels": {
                "app": self.app_name,
                "version": self.version,
            },
        }
        res["spec"].setdefault("template", {})
        res["spec"]["template"].setdefault("metadata", {})
        res["spec"]["template"]["metadata"]["annotations"] = {
            SM_INJECT_ANNOTATION: "true"
        }
        res["spec"]["template"]["metadata"]["labels"] = {
            "app": self.app_name,
            "version": self.version,
        }
        res["spec"]["template"].setdefault("spec", {})
        res["spec"]["template"]["spec"]["containers"] = [
            {
                "image": self.image,
                "imagePullPolicy": self.policy,
                "name": self.name,
            }
        ]
        res["spec"]["template"]["spec"]["restartPolicy"] = "Always"
        if self.strategy:
            res["spec"]["strategy"] = self.strategy
        if self.service_account:
            res["spec"]["template"]["spec"]["serviceAccountName"] = self.app_name
        if self.command:
            res["spec"]["template"]["spec"]["containers"][0]["command"] = self.command
        if self.port:
            res["spec"]["template"]["spec"]["containers"][0]["ports"] = [
                {"containerPort": self.port}
            ]
        return res


class ServiceMeshMemberRollForTests(ServiceMeshMemberRoll):
    def __init__(
        self,
        members,
    ):
        """
        Service Mesh Member Roll creation
        Args:
            members (list): Namespaces to be added to SM
        """
        super().__init__(
            name=SMMR_NAME,
            namespace=ISTIO_SYSTEM_DEFAULT_NS,
        )
        self.members = members

    def to_dict(self):
        res = super().to_dict()
        res["spec"] = {"members": self.members}
        return res


def wait_sm_components_convergence(vm, server, destination):
    server_response = None
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_1MIN,
            sleep=5,
            func=traffic_management_request,
            vm=vm,
            server=server,
            destination=destination,
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
def istio_system_namespace(admin_client):
    for ns in Namespace.get(
        name=ISTIO_SYSTEM_DEFAULT_NS,
        dyn_client=admin_client,
    ):
        return ns

    pytest.skip(
        msg=f"Couldn't get {ISTIO_SYSTEM_DEFAULT_NS}. Service Mesh is not installed"
    )


@pytest.fixture(scope="module")
def service_mesh_member_roll(namespace):
    with ServiceMeshMemberRollForTests(members=[namespace.name]) as smmr:
        yield smmr


@pytest.fixture(scope="module")
def vm_cirros_with_sm_annotation(
    unprivileged_client,
    namespace,
    service_mesh_member_roll,
):
    vm_name = "sm-vm"
    with CirrosVirtualMachinefForServiceMesh(
        client=unprivileged_client,
        name=vm_name,
        namespace=namespace.name,
    ) as vm:
        vm.custom_service_enable(
            service_name=vm_name,
            port=SM_PORT,
        )
        running_vm(vm=vm, wait_for_interfaces=False)
        yield vm


@pytest.fixture(scope="class")
def server_deployment_v1(namespace):
    with ServiceMeshDeployments(
        name=SERVER_DEMO_NAME,
        namespace=namespace.name,
        version=VERSION_1_DEPLOYMENT,
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
def server_service_sm(server_deployment_v1):
    with SMDeploymentService(
        app_name=server_deployment_v1.app_name,
        namespace=server_deployment_v1.namespace,
        port=server_deployment_v1.service_port,
    ) as sv:
        yield sv


@pytest.fixture(scope="class")
def gateway_sm(server_deployment_v1):
    with GatewayForTests(
        app_name=server_deployment_v1.app_name,
        namespace=server_deployment_v1.namespace,
        hosts=[server_deployment_v1.host],
    ) as gw:
        yield gw


@pytest.fixture(scope="class")
def virtual_service_sm(server_deployment_v1, gateway_sm):
    with VirtualServiceForTests(
        app_name=server_deployment_v1.app_name,
        namespace=server_deployment_v1.namespace,
        hosts=[server_deployment_v1.host],
        gateways=[gateway_sm.name],
        subset=server_deployment_v1.version,
        port=server_deployment_v1.service_port,
    ) as vsv:
        yield vsv


@pytest.fixture(scope="class")
def destination_rule_sm(server_deployment_v1, server_deployment_v2):
    with DestinationRuleForTests(
        app_name=server_deployment_v1.app_name,
        namespace=server_deployment_v1.namespace,
        versions=[server_deployment_v1.version, server_deployment_v2.version],
    ) as dr:
        yield dr


@pytest.fixture(scope="class")
def traffic_management_sm_convergence(
    istio_system_namespace,
    vm_cirros_with_sm_annotation,
    server_deployment_v1,
    server_deployment_v2,
    server_service_sm,
    gateway_sm,
    destination_rule_sm,
    virtual_service_sm,
    sm_ingress_service_addr,
):
    wait_sm_components_convergence(
        vm=vm_cirros_with_sm_annotation,
        server=server_deployment_v1,
        destination=sm_ingress_service_addr,
    )


@pytest.fixture(scope="class")
def sm_ingress_service_addr(admin_client, istio_system_namespace):
    for svc in Service.get(
        dyn_client=admin_client,
        name=INGRESS_SERVICE,
        namespace=istio_system_namespace.name,
    ):
        return svc.instance.spec.clusterIP


@pytest.fixture()
def change_routing_to_v2(virtual_service_sm, server_deployment_v2):
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
    ResourceEditor(patches={virtual_service_sm: patch}).update()
