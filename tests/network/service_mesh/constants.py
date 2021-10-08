import shlex


SMMR_NAME = "default"
HTTP_BIN_SERVICE_NAME = "httpbin"
IN_MESH_NS = "in-mesh"
ISTIO_SYSTEM_DEFAULT_NS = "istio-system"
SERVER_DEMO_HOST = "server-demo.example.com"
SERVER_DEMO_NAME = "server-demo"
SM_INJECT_ANNOTATION = (
    "sidecar.istio.io/inject"  # A proxy will be automatically injected into a pod
)
VERSION_1_DEPLOYMENT = "v1"
VERSION_2_DEPLOYMENT = "v2"
CIRROS_IMAGE = "quay.io/kubevirt/cirros-container-disk-demo"
SM_PORT = 8000
HTTPBIN_IMAGE = "docker.io/kennethreitz/httpbin"
HTTPBIN_COMMAND = shlex.split("gunicorn -b 0.0.0.0:8000 httpbin:app -k gevent")
SERVER_DEPLOYMENT_STRATEGY = {
    "rollingUpdate": {"maxSurge": 1, "maxUnavailable": 1},
    "type": "RollingUpdate",
}
SERVER_IMAGE = "quay.io/openshift-cnv/qe-cnv-service-mesh-server-demo"
SERVER_V1_IMAGE = f"{SERVER_IMAGE}:{VERSION_1_DEPLOYMENT}.0"
SERVER_V2_IMAGE = f"{SERVER_IMAGE}:{VERSION_2_DEPLOYMENT}.0"
GATEWAY_SELECTOR = {"istio": "ingressgateway"}
PORT_80 = 80
SSH_PORT = 22
PORT_8080 = 8080
HTTP_PROTOCOL = "HTTP"
SERVICE_TYPE = "service"
GATEWAY_TYPE = "gw"
DESTINATION_RULE_TYPE = "dr"
VIRTUAL_SERVICE_TYPE = "vs"
PEER_AUTHENTICATION_TYPE = "pa"
DEPLOYMENT_TYPE = "dp"
SM_VM_MEMORY_REQ = "128M"
INGRESS_SERVICE = "istio-ingressgateway"
