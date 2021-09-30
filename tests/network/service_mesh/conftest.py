import time

from ocp_resources.deployment import Deployment
from ocp_resources.destination_rule import DestinationRule
from ocp_resources.gateway import Gateway
from ocp_resources.peer_authentication import PeerAuthentication
from ocp_resources.service import Service
from ocp_resources.service_mesh_member_roll import ServiceMeshMemberRoll
from ocp_resources.virtual_service import VirtualService

from tests.network.service_mesh.constants import (
    CIRROS_IMAGE,
    DEPLOYMENT_TYPE,
    DESTINATION_RULE_TYPE,
    GATEWAY_SELECTOR,
    GATEWAY_TYPE,
    HTTP_PROTOCOL,
    ISTIO_SYSTEM_DEFAULT_NS,
    PEER_AUTHENTICATION_TYPE,
    PORT_80,
    SERVICE_TYPE,
    SM_INJECT_ANNOTATION,
    SM_PORT,
    SMMR_NAME,
    VIRTUAL_SERVICE_TYPE,
)
from utilities.constants import OS_FLAVOR_CIRROS, Images
from utilities.virt import VirtualMachineForTests


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
            memory_requests=Images.Cirros.DEFAULT_MEMORY_SIZE,
            image=CIRROS_IMAGE,
        )
        self.interface_port = interface_port

    def to_dict(self):
        res = super().to_dict()
        res["metadata"]["annotations"] = {
            SM_INJECT_ANNOTATION: "true",
        }
        res["spec"]["domain"] = {
            "devices": {
                "interfaces": [
                    {
                        "name": "default",
                        "masquerade": {},
                        "ports": [
                            {
                                "port": self.interface_port,
                            },
                        ],
                    },
                ],
            },
        }

        return res


class SMDeploymentService(Service):
    def __init__(self, app_name, namespace, port, port_name=None):
        self.name = unique_name(name=app_name, type=SERVICE_TYPE)
        super().__init__(
            name=self.name,
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
