# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV CDI tests
"""

import logging
import os

import pytest
from ocp_resources.configmap import ConfigMap
from ocp_resources.datavolume import DataVolume
from ocp_resources.deployment import Deployment
from ocp_resources.resource import ResourceEditor
from ocp_resources.route import Route
from ocp_resources.secret import Secret
from ocp_resources.storage_class import StorageClass
from pytest_testconfig import config as py_config

from tests.storage.utils import HttpService, smart_clone_supported_by_sc
from utilities.infra import (
    INTERNAL_HTTP_SERVER_ADDRESS,
    Images,
    get_cert,
    hco_cr_jsonpatch_annotations_dict,
)
from utilities.storage import (
    HttpDeployment,
    downloaded_image,
    sc_volume_binding_mode_is_wffc,
    virtctl_upload_dv,
)


LOGGER = logging.getLogger(__name__)
LOCAL_PATH = f"/tmp/{Images.Cdi.QCOW2_IMG}"


@pytest.fixture()
def cdi_resources(request, admin_client):
    rcs_object = request.param["resource"]
    LOGGER.info(f"Get all resources with kind: {rcs_object.kind}")
    resource_list = list(rcs_object.get(dyn_client=admin_client))
    return [rcs for rcs in resource_list if rcs.name.startswith("cdi-")]


@pytest.fixture(scope="module")
def internal_http_configmap(namespace):
    path = os.path.join("tests/storage/internal_http/certs", "tls.crt")
    with open(path, "r") as cert_content:
        with ConfigMap(
            name="internal-https-configmap",
            namespace=namespace.name,
            data={"tlsregistry.crt": cert_content.read()},
        ) as configmap:
            yield configmap


@pytest.fixture(scope="module")
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
        dep.wait_for_replicas()
        yield dep


@pytest.fixture(scope="session")
def internal_http_service():
    with HttpService(name="internal-http", namespace="kube-system") as svc:
        yield svc


@pytest.fixture(scope="session")
def images_internal_http_server(internal_http_deployment, internal_http_service):
    return {
        "http": f"http://{INTERNAL_HTTP_SERVER_ADDRESS}/",
        "https": f"https://{INTERNAL_HTTP_SERVER_ADDRESS}/",
        "http_auth": f"http://{INTERNAL_HTTP_SERVER_ADDRESS}:81/",
    }


@pytest.fixture(scope="session")
def images_private_registry_server():
    return py_config["servers"]["registry_server"]


@pytest.fixture()
def upload_proxy_route(admin_client):
    routes = Route.get(admin_client)
    upload_route = None
    for route in routes:
        if route.exposed_service == "cdi-uploadproxy":
            upload_route = route
    assert upload_route is not None
    yield upload_route


@pytest.fixture(scope="session")
def skip_no_default_sc(default_sc):
    """
    Skip test if no default Storage Class defined
    """
    if not default_sc:
        pytest.skip("Skipping test, no default storage class configured")


@pytest.fixture(scope="session")
def hpp_storage_class(cluster_storage_classes):
    """
    Get the HPP storage class if configured
    """
    for sc in cluster_storage_classes:
        if sc.name == StorageClass.Types.HOSTPATH:
            return sc


@pytest.fixture(scope="session")
def skip_test_if_no_hpp_sc(hpp_storage_class):
    if not hpp_storage_class:
        pytest.skip("Skipping test, HostPath storage class is not deployed")


@pytest.fixture(scope="session")
def skip_when_hpp_no_waitforfirstconsumer(skip_test_if_no_hpp_sc):
    if not sc_volume_binding_mode_is_wffc(sc=StorageClass.Types.HOSTPATH):
        pytest.skip(msg="Test only run when volumeBindingMode is WaitForFirstConsumer")


@pytest.fixture()
def uploadproxy_route_deleted(hco_namespace):
    """
    Delete uploadproxy route from kubevirt-hyperconverged namespace.

    This scales down cdi-operator replicas to 0 so that the route is not auto-created by the cdi-operator pod.
    Once the cdi-operator is terminated, route is deleted to perform the test.
    """
    ns = hco_namespace.name
    deployment = Deployment(name="cdi-operator", namespace=ns)
    try:
        deployment.scale_replicas(replica_count=0)
        deployment.wait_for_replicas(deployed=False)
        Route(name="cdi-uploadproxy", namespace=ns).delete(wait=True)
        yield
    finally:
        deployment.scale_replicas(replica_count=1)
        deployment.wait_for_replicas()
        Route(name="cdi-uploadproxy", namespace=ns).wait()


@pytest.fixture()
def cdi_config_upload_proxy_overridden(
    hco_namespace,
    hyperconverged_resource_scope_function,
    cdi_config,
    upload_proxy_route,
):
    new_upload_proxy_url = f"newuploadroute-cdi-{hco_namespace.name}.apps.working.oc4"
    with ResourceEditor(
        patches={
            hyperconverged_resource_scope_function: hco_cr_jsonpatch_annotations_dict(
                component="cdi",
                path="uploadProxyURLOverride",
                value=new_upload_proxy_url,
            )
        },
    ):
        cdi_config.wait_until_upload_url_changed(uploadproxy_url=new_upload_proxy_url)
        yield


@pytest.fixture()
def new_route_created(hco_namespace):
    existing_route = Route(name="cdi-uploadproxy", namespace=hco_namespace.name)
    route = Route(
        name="newuploadroute-cdi",
        namespace=hco_namespace.name,
        destination_ca_cert=existing_route.ca_cert,
        service="cdi-uploadproxy",
    )
    route.create(wait=True)
    yield
    route.delete(wait=True)


@pytest.fixture()
def https_config_map(request, namespace):
    data = (
        {"ca.pem": request.param["data"]}
        if hasattr(request, "param")
        else {"ca.pem": get_cert(server_type="https_cert")}
    )
    with ConfigMap(
        name="https-cert",
        namespace=namespace.name,
        data=data,
    ) as configmap:
        yield configmap


@pytest.fixture()
def registry_config_map(namespace):
    with ConfigMap(
        name="registry-cert",
        namespace=namespace.name,
        data={"tlsregistry.crt": get_cert(server_type="registry_cert")},
    ) as configmap:
        yield configmap


@pytest.fixture()
def uploaded_dv(
    request,
    namespace,
    storage_class_matrix__class__,
    tmpdir,
):
    storage_class = [*storage_class_matrix__class__][0]
    image_file = request.param.get("image_file")
    dv_name = image_file.split(".")[0].replace("_", "-").lower()
    local_path = f"{tmpdir}/{image_file}"
    downloaded_image(
        remote_name=request.param.get("remote_name"), local_name=local_path
    )
    with virtctl_upload_dv(
        namespace=namespace.name,
        name=dv_name,
        size=request.param.get("dv_size"),
        storage_class=storage_class,
        image_path=local_path,
        insecure=True,
    ) as res:
        status, out, _ = res
        LOGGER.info(out)
        assert status
        dv = DataVolume(namespace=namespace.name, name=dv_name)
        dv.wait(timeout=60)
        assert dv.pvc.bound()
        yield dv
        dv.delete(wait=True)
        # We do not want 11-30G~ files in /tmp
        # Pytest will only cleanup every 3 tmpdir calls
        try:
            LOGGER.info("Deleting image file from tmpdir")
            os.remove(os.path.join(tmpdir, image_file))
        except OSError as e:
            LOGGER.error(e)
            raise


@pytest.fixture()
def download_image():
    downloaded_image(
        remote_name=f"{Images.Cdi.DIR}/{Images.Cdi.QCOW2_IMG}", local_name=LOCAL_PATH
    )


@pytest.fixture()
def skip_smart_clone_not_supported_by_sc(
    data_volume_multi_storage_scope_function, admin_client
):
    if smart_clone_supported_by_sc(
        sc=data_volume_multi_storage_scope_function.storage_class,
        client=admin_client,
    ):
        return
    pytest.skip(
        f"Smart clone via snapshots not supported by {data_volume_multi_storage_scope_function.storage_class}"
    )


def _skip_block_volumemode(storage_class_matrix):
    storage_class = [*storage_class_matrix][0]
    if storage_class_matrix[storage_class]["volume_mode"] == "Block":
        pytest.skip("Test is not supported on Block volume mode")


@pytest.fixture()
def skip_block_volumemode_scope_function(storage_class_matrix__function__):
    _skip_block_volumemode(storage_class_matrix=storage_class_matrix__function__)


@pytest.fixture(scope="module")
def skip_block_volumemode_scope_module(storage_class_matrix__module__):
    _skip_block_volumemode(storage_class_matrix=storage_class_matrix__module__)


@pytest.fixture()
def default_fs_overhead(cdi_config):
    return float(cdi_config.instance.status.filesystemOverhead["global"])
