# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV CDI tests
"""

import base64
import logging
import os

import pytest
from ocp_resources.configmap import ConfigMap
from ocp_resources.daemonset import DaemonSet
from ocp_resources.deployment import Deployment
from ocp_resources.hostpath_provisioner import HostPathProvisioner
from ocp_resources.resource import ResourceEditor
from ocp_resources.route import Route
from ocp_resources.secret import Secret
from ocp_resources.storage_class import StorageClass
from ocp_resources.utils import TimeoutSampler
from openshift.dynamic.exceptions import ResourceNotFoundError
from pytest_testconfig import config as py_config

from tests.storage.utils import HttpService, smart_clone_supported_by_sc
from utilities.constants import CDI_OPERATOR, CDI_UPLOADPROXY, Images
from utilities.infra import (
    INTERNAL_HTTP_SERVER_ADDRESS,
    get_cert,
    hco_cr_jsonpatch_annotations_dict,
    is_bug_open,
)
from utilities.storage import (
    HttpDeployment,
    downloaded_image,
    sc_volume_binding_mode_is_wffc,
)


LOGGER = logging.getLogger(__name__)
LOCAL_PATH = f"/tmp/{Images.Cdi.QCOW2_IMG}"
ROUTER_CERT_NAME = "router.crt"


@pytest.fixture()
def cdi_resources(request, admin_client):
    rcs_object = request.param
    LOGGER.info(f"Get all resources with kind: {rcs_object.kind}")
    resource_list = list(rcs_object.get(dyn_client=admin_client))
    return [rcs for rcs in resource_list if rcs.name.startswith("cdi-")]


@pytest.fixture()
def hpp_resources(request, admin_client):
    rcs_object = request.param
    LOGGER.info(f"Get all resources with kind: {rcs_object.kind}")
    resource_list = list(rcs_object.get(dyn_client=admin_client))
    return [rcs for rcs in resource_list if rcs.name.startswith("hostpath-")]


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
        if route.exposed_service == CDI_UPLOADPROXY:
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
    deployment = Deployment(name=CDI_OPERATOR, namespace=ns)
    try:
        deployment.scale_replicas(replica_count=0)
        deployment.wait_for_replicas(deployed=False)
        Route(name=CDI_UPLOADPROXY, namespace=ns).delete(wait=True)
        yield
    finally:
        deployment.scale_replicas(replica_count=1)
        deployment.wait_for_replicas()
        Route(name=CDI_UPLOADPROXY, namespace=ns).wait()


@pytest.fixture()
def cdi_config_upload_proxy_overridden(
    hco_namespace,
    hyperconverged_resource_scope_function,
    cdi_config,
    new_route_created,
):
    with ResourceEditor(
        patches={
            hyperconverged_resource_scope_function: hco_cr_jsonpatch_annotations_dict(
                component="cdi",
                path="uploadProxyURLOverride",
                value=new_route_created.host,
            )
        },
    ):
        cdi_config.wait_until_upload_url_changed(uploadproxy_url=new_route_created.host)
        yield


@pytest.fixture()
def new_route_created(hco_namespace):
    existing_route = Route(name=CDI_UPLOADPROXY, namespace=hco_namespace.name)
    route = Route(
        name="newuploadroute-cdi",
        namespace=hco_namespace.name,
        destination_ca_cert=existing_route.ca_cert,
        service=CDI_UPLOADPROXY,
    )
    route.create(wait=True)
    yield route
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


@pytest.fixture(scope="module")
def skip_if_hpp_not_in_sc_options(request):
    storage_class_matrix = request.session.config.getoption(name="storage_class_matrix")
    if storage_class_matrix and StorageClass.Types.HOSTPATH not in storage_class_matrix:
        pytest.skip("This test run only on hostpath-provisioner storage class")


@pytest.fixture()
def unset_predefined_scratch_sc(hyperconverged_resource_scope_module, cdi_config):
    if cdi_config.instance.spec.scratchSpaceStorageClass:
        empty_scratch_space_spec = {"spec": {"scratchSpaceStorageClass": ""}}
        with ResourceEditor(
            patches={hyperconverged_resource_scope_module: empty_scratch_space_spec}
        ):
            LOGGER.info(f"wait for {empty_scratch_space_spec} in CDIConfig")
            for sample in TimeoutSampler(
                wait_timeout=20,
                sleep=1,
                func=lambda: not cdi_config.instance.spec.scratchSpaceStorageClass,
            ):
                if sample:
                    break
            yield
    else:
        yield


@pytest.fixture()
def default_sc_as_fallback_for_scratch(
    unset_predefined_scratch_sc, admin_client, cdi_config, default_sc
):
    # Based on py_config["default_storage_class"], update default SC, if needed
    if default_sc:
        yield default_sc
    else:
        for sc in StorageClass.get(
            dyn_client=admin_client, name=py_config["default_storage_class"]
        ):
            assert (
                sc
            ), f'The cluster does not include {py_config["default_storage_class"]} storage class'
            with ResourceEditor(
                patches={
                    sc: {
                        "metadata": {
                            "annotations": {
                                StorageClass.Annotations.IS_DEFAULT_CLASS: "true"
                            },
                            "name": sc.name,
                        }
                    }
                }
            ):
                yield sc


@pytest.fixture()
def router_cert_secret(admin_client):
    router_secret = "router-certs-default"
    for secret in Secret.get(
        dyn_client=admin_client,
        name=router_secret,
        namespace="openshift-ingress",
    ):
        return secret
    raise ResourceNotFoundError(f"secret: {router_secret} not found")


@pytest.fixture()
def temp_router_cert(tmpdir, router_cert_secret):
    router_cert_path = f"{tmpdir}/{ROUTER_CERT_NAME}"
    with open(router_cert_path, "w") as the_file:
        the_file.write(
            (
                base64.standard_b64decode(router_cert_secret.instance.data["tls.crt"])
            ).decode("utf-8")
        )
    yield router_cert_path


@pytest.fixture()
def enabled_ca(temp_router_cert):
    update_ca_trust_command = "sudo update-ca-trust"
    ca_path = "/etc/pki/ca-trust/source/anchors/"
    # copy to the trusted secure list and update
    os.popen(f"sudo cp {temp_router_cert} {ca_path}")
    os.popen(update_ca_trust_command)
    yield
    os.popen(f"sudo rm {ca_path}{ROUTER_CERT_NAME}")
    os.popen(update_ca_trust_command)


@pytest.fixture(scope="session")
def hpp_daemonset(hco_namespace):
    daemonset = DaemonSet(
        name=HostPathProvisioner.Name.HOSTPATH_PROVISIONER,
        namespace=hco_namespace.name,
    )
    assert daemonset.exists, "hpp_daemonset does not exist"
    yield daemonset


@pytest.fixture(scope="module")
def skip_if_post_cnv_upgrade_cluster_and_labels_bug_not_closed(
    is_post_cnv_upgrade_cluster,
):
    if (is_bug_open(bug_id=2017478)) and is_post_cnv_upgrade_cluster:
        pytest.skip("Skip labels test on post cnv upgrade cluster")


@pytest.fixture()
def skip_if_sc_volume_binding_mode_is_wffc(storage_class_matrix__module__):
    storage_class = [*storage_class_matrix__module__][0]
    if sc_volume_binding_mode_is_wffc(sc=storage_class):
        pytest.skip(
            "Test does not support storage class with WaitForFirstConsumer binding mode"
        )
