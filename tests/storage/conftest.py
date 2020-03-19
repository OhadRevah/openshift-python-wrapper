# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV CDI tests
"""

import logging
import os

import pytest
from pytest_testconfig import config as py_config
from resources.cdi import CDI
from resources.cdi_config import CDIConfig
from resources.configmap import ConfigMap
from resources.deployment import Deployment, HttpDeployment
from resources.resource import ResourceEditor
from resources.route import Route
from resources.secret import Secret
from resources.storage_class import StorageClass
from tests.storage.utils import HttpService
from utilities.infra import get_cert


LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def cdi_resources(request, default_client):
    rcs_object = request.param["resource"]
    LOGGER.info(f"Get all resources with kind: {rcs_object.kind}")
    resource_list = list(rcs_object.get(dyn_client=default_client))
    return [rcs for rcs in resource_list if rcs.name.startswith("cdi-")]


@pytest.fixture(scope="session")
def internal_http_configmap(namespace):
    path = os.path.join("tests/storage/internal_http/certs", "tls.crt")
    with open(path, "r") as cert_content:
        with ConfigMap(
            name="internal-https-configmap",
            namespace=namespace.name,
            data=cert_content.read(),
        ) as configmap:
            yield configmap


@pytest.fixture(scope="session")
def internal_http_secret(namespace):
    with Secret(
        name="internal-http-secret",
        namespace=namespace.name,
        accesskeyid="YWRtaW4=",
        secretkey="cGFzc3dvcmQ=",
    ) as secret:
        yield secret


@pytest.fixture(scope="session")
def internal_http_deployment():
    """
    Deploy internal HTTP server Deployment into the kube-system namespace.
    This Deployment deploys a pod that runs an HTTP server
    """
    with HttpDeployment(name="internal-http", namespace="kube-system") as dep:
        dep.wait_until_avail_replicas()
        yield dep


@pytest.fixture(scope="session")
def internal_http_service():
    with HttpService(name="internal-http", namespace="kube-system") as svc:
        yield svc


@pytest.fixture(scope="session")
def images_internal_http_server(internal_http_deployment, internal_http_service):
    server_address = "internal-http.kube-system"
    return {
        "http": f"http://{server_address}/",
        "https": f"https://{server_address}/",
        "http_auth": f"http://{server_address}:81/",
    }


@pytest.fixture(scope="session")
def images_private_registry_server():
    return py_config[py_config["region"]]["registry_server"]


@pytest.fixture()
def upload_proxy_route(default_client):
    routes = Route.get(default_client)
    upload_route = None
    for route in routes:
        if route.exposed_service == "cdi-uploadproxy":
            upload_route = route
    assert upload_route is not None
    yield upload_route


@pytest.fixture(scope="session")
def default_sc(default_client):
    """
    Get default Storage Class defined
    """
    for sc in StorageClass.get(default_client):
        if (
            sc.instance.metadata.get("annotations", {}).get(
                "storageclass.kubernetes.io/is-default-class"
            )
            == "true"
        ):
            return sc


@pytest.fixture(scope="session")
def skip_no_default_sc(default_sc):
    """
    Skip test if no default Storage Class defined
    """
    if not default_sc:
        pytest.skip("Skipping test, no default storage class configured")


@pytest.fixture(scope="session")
def hpp_storage_class(default_client):
    """
    Get the HPP storage class if configured
    """
    for sc in StorageClass.get(default_client):
        if sc.instance.metadata.get("name") == StorageClass.Types.HOSTPATH:
            return sc


@pytest.fixture(scope="session")
def skip_test_if_no_hpp_sc(hpp_storage_class):
    LOGGER.debug("Use 'skip_test_if_no_hpp_sc' fixture...")
    if not hpp_storage_class:
        pytest.skip("Skipping test, HostPath storage class is not deployed")


@pytest.fixture(scope="session")
def cdi_config():
    cdi_config = CDIConfig("config")
    assert cdi_config.instance is not None
    return cdi_config


@pytest.fixture()
def uploadproxy_route_deleted():
    """
    Delete uploadproxy route from kubevirt-hyperconverged namespace.

    This scales down cdi-operator replicas to 0 so that the route is not auto-created by the cdi-operator pod.
    Once the cdi-operator is terminated, route is deleted to perform the test.
    """
    ns = py_config["hco_namespace"]
    deployment = Deployment(name="cdi-operator", namespace=ns)
    try:
        deployment.scale_replicas(replica_count=0)
        deployment.wait_until_no_replicas()
        Route(name="cdi-uploadproxy", namespace=ns).delete(wait=True)
        yield
    finally:
        deployment.scale_replicas(replica_count=1)
        deployment.wait_until_avail_replicas()
        Route(name="cdi-uploadproxy", namespace=ns).wait()


@pytest.fixture()
def cdi_config_upload_proxy_overridden(upload_proxy_route):
    cdi_config = CDIConfig("config")
    assert cdi_config.instance is not None
    new_upload_proxy_url = (
        f"newuploadroute-cdi-{py_config['hco_namespace']}.apps.working.oc4"
    )
    with ResourceEditor(
        {cdi_config: {"spec": {"uploadProxyURLOverride": new_upload_proxy_url}}}
    ):
        cdi_config.wait_until_upload_url_changed(new_upload_proxy_url)


@pytest.fixture()
def new_route_created():
    existing_route = Route(name="cdi-uploadproxy", namespace=py_config["hco_namespace"])
    route = Route(
        name="newuploadroute-cdi",
        namespace=py_config["hco_namespace"],
        destination_ca_cert=existing_route.ca_cert,
        service="cdi-uploadproxy",
    )
    route.create(wait=True)
    yield
    route.delete(wait=True)


@pytest.fixture(scope="session")
def cdi():
    cdi = CDI("cdi-kubevirt-hyperconverged", py_config["hco_namespace"])
    assert cdi.instance is not None
    yield cdi


@pytest.fixture()
def https_config_map(namespace):
    with ConfigMap(
        name="https-cert",
        namespace=namespace.name,
        cert_name="ca.pem",
        data=get_cert("https_cert"),
    ) as configmap:
        yield configmap


@pytest.fixture()
def registry_config_map(namespace):
    with ConfigMap(
        name="registry-cert", namespace=namespace.name, data=get_cert("registry_cert")
    ) as configmap:
        yield configmap
