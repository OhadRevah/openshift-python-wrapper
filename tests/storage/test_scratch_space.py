# -*- coding: utf-8 -*-

import logging
import threading

import pytest
from openshift.dynamic.exceptions import NotFoundError
from pytest_testconfig import config as py_config
from resources.configmap import ConfigMap
from resources.datavolume import (
    ImportFromHttpDataVolume,
    ImportFromRegistryDataVolume,
    UploadDataVolume,
)
from resources.persistent_volume_claim import PersistentVolumeClaim
from resources.secret import Secret
from resources.upload_token_request import UploadTokenRequest
from resources.utils import TimeoutSampler
from tests.storage import utils as storage_utils
from utilities.infra import get_cert


LOGGER = logging.getLogger(__name__)
CDI_IMAGES_DIR = "cdi-test-images/cirros_images/"
PRIVATE_REGISTRY_IMAGE = "cirros-registry-disk-demo:latest"
RAW_IMAGE = "cirros-0.4.0-x86_64-disk.raw"
RAW_GZ_IMAGE = "cirros-0.4.0-x86_64-disk.raw.gz"
RAW_XZ_IMAGE = "cirros-0.4.0-x86_64-disk.raw.xz"
QCOW2_IMG = "cirros-0.4.0-x86_64-disk.qcow2"
QCOW2_IMG_GZ = "cirros-0.4.0-x86_64-disk.qcow2.gz"
QCOW2_IMG_XZ = "cirros-0.4.0-x86_64-disk.qcow2.xz"

pytestmark = pytest.mark.skipif(
    py_config["distribution"] == "upstream",
    reason="importing only from local http/https and registry servers for d/s",
)


@pytest.mark.parametrize(
    ("dv_name", "file_name", "content_type", "size"),
    [
        pytest.param(
            "no-scratch-space-import-raw-https",
            RAW_IMAGE,
            ImportFromHttpDataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
        ),
        pytest.param(
            "no-scratch-space-import-raw-gz-https",
            RAW_GZ_IMAGE,
            ImportFromHttpDataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
        ),
        pytest.param(
            "no-scratch-space-import-raw-xz-https",
            RAW_XZ_IMAGE,
            ImportFromHttpDataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
        ),
    ],
    ids=[
        "no-scratch-space-import-raw-https",
        "no-scratch-space-import-raw-gz-https",
        "no-scratch-space-import-raw-xz-https",
    ],
)
def test_no_scratch_space_import_https_data_volume(
    storage_ns, images_https_server, dv_name, file_name, content_type, size
):
    url = get_file_url_https_server(images_https_server, file_name)
    with ConfigMap(
        name="https-cert-configmap",
        namespace=storage_ns.name,
        data=get_cert("https_cert"),
    ) as configmap:
        create_dv_and_vm_no_scratch_space(
            dv_name, storage_ns.name, url, configmap.name, None, content_type, size
        )


@pytest.mark.parametrize(
    ("dv_name", "file_name"),
    [
        pytest.param(
            "scratch-space-import-qcow2-https",
            QCOW2_IMG,
            marks=(pytest.mark.polarion("CNV-2323")),
        ),
        pytest.param(
            "scratch-space-import-qcow2gz-https",
            QCOW2_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2323")),
        ),
        pytest.param(
            "scratch-space-import-qcow2xz-https",
            QCOW2_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-2323")),
        ),
    ],
    ids=[
        "scratch-space-import-qcow2-https",
        "scratch-space-import-qcow2gz-https",
        "scratch-space-import-qcow2xz-https",
    ],
)
def test_scratch_space_import_https_data_volume(
    storage_ns, images_https_server, dv_name, file_name
):
    url = get_file_url_https_server(images_https_server, file_name)
    with ConfigMap(
        name="https-cert-configmap",
        namespace=storage_ns.name,
        data=get_cert("https_cert"),
    ) as configmap:
        create_dv_and_vm(
            server_type="https",
            dv_name=dv_name,
            namespace=storage_ns.name,
            url=url,
            configmap=configmap.name,
            content_type=ImportFromHttpDataVolume.ContentType.KUBEVIRT,
            size="5Gi",
        )


@pytest.mark.parametrize(
    ("dv_name", "file_name", "content_type", "size"),
    [
        pytest.param(
            "no-scratch-space-import-raw-http-basic-auth",
            RAW_IMAGE,
            ImportFromHttpDataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
        ),
        pytest.param(
            "no-scratch-space-import-raw-gz-http-basic-auth",
            RAW_GZ_IMAGE,
            ImportFromHttpDataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
        ),
        pytest.param(
            "no-scratch-space-import-raw-xz-http-basic-auth",
            RAW_XZ_IMAGE,
            ImportFromHttpDataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
        ),
    ],
    ids=[
        "no-scratch-space-import-raw-http-auth",
        "no-scratch-space-import-raw-gz-http-auth",
        "no-scratch-space-import-raw-xz-http-auth",
    ],
)
def test_no_scratch_space_import_http_basic_auth(
    storage_ns, images_external_http_server, dv_name, file_name, content_type, size
):
    url = get_file_url_http_server_basic_auth(images_external_http_server, file_name)
    with Secret(
        name="https-secret",
        namespace=storage_ns.name,
        accesskeyid="cmVkaGF0",
        secretkey="MTIz",
    ) as secret:
        create_dv_and_vm_no_scratch_space(
            dv_name, storage_ns.name, url, None, secret.name, content_type, size
        )


@pytest.mark.parametrize(
    ("dv_name", "file_name", "content_type", "size"),
    [
        pytest.param(
            "no-scratch-space-import-raw-http",
            RAW_IMAGE,
            ImportFromHttpDataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
        ),
        pytest.param(
            "no-scratch-space-import-raw-gz-http",
            RAW_GZ_IMAGE,
            ImportFromHttpDataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
        ),
        pytest.param(
            "no-scratch-space-import-raw-xz-http",
            RAW_XZ_IMAGE,
            ImportFromHttpDataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
        ),
    ],
    ids=[
        "no-scratch-space-import-raw-http",
        "no-scratch-space-import-raw-gz-http",
        "no-scratch-space-import-raw-xz-http",
    ],
)
def test_no_scratch_space_import_http(
    storage_ns, images_external_http_server, dv_name, file_name, content_type, size
):
    url = get_file_url_http_server(images_external_http_server, file_name)
    create_dv_and_vm_no_scratch_space(
        dv_name, storage_ns.name, url, None, None, content_type, size
    )


@pytest.mark.parametrize(
    ("file_name", "dv_name"),
    [
        pytest.param(QCOW2_IMG, "cnv-2315", marks=(pytest.mark.polarion("CNV-2315"))),
        pytest.param(
            QCOW2_IMG_GZ, "cnv-2315", marks=(pytest.mark.polarion("CNV-2315"))
        ),
        pytest.param(
            QCOW2_IMG_XZ, "cnv-2315", marks=(pytest.mark.polarion("CNV-2315"))
        ),
        pytest.param(RAW_IMAGE, "cnv-2315", marks=(pytest.mark.polarion("CNV-2315"))),
        pytest.param(
            RAW_XZ_IMAGE, "cnv-2315", marks=(pytest.mark.polarion("CNV-2315"))
        ),
        pytest.param(
            RAW_GZ_IMAGE, "cnv-2315", marks=(pytest.mark.polarion("CNV-2315"))
        ),
    ],
)
def test_scratch_space_upload_data_volume(storage_ns, tmpdir, file_name, dv_name):
    local_name = f"{tmpdir}/{file_name}"
    remote_name = f"{CDI_IMAGES_DIR}{file_name}"
    storage_utils.downloaded_image(remote_name=remote_name, local_name=local_name)
    with UploadDataVolume(
        name=dv_name,
        namespace=storage_ns.name,
        size="3Gi",
        storage_class=py_config["storage_defaults"]["storage_class"],
    ) as dv:
        dv.wait_for_status(status=UploadDataVolume.Status.UPLOAD_READY, timeout=180)
        with UploadTokenRequest(name="cnv-2315", namespace=storage_ns.name) as utr:
            token = utr.create().status.token
            LOGGER.info("Ensure upload was successful")
            sampler = TimeoutSampler(
                timeout=120,
                sleep=5,
                func=storage_utils.upload_image,
                token=token,
                data=local_name,
            )
            for sample in sampler:
                if sample == 200:
                    scratch_pvc = PersistentVolumeClaim(
                        name=f"{dv.name}-scratch", namespace=dv.namespace
                    )
                    scratch_pvc.wait_for_status(
                        status=PersistentVolumeClaim.Status.BOUND, timeout=300
                    )
                    dv.wait_for_status(status=dv.Status.SUCCEEDED, timeout=300)
                    storage_utils.create_vm_with_dv(dv)
                    return True


@pytest.mark.polarion("CNV-2319")
def test_scratch_space_import_registry_data_volume(
    storage_ns, images_private_registry_server
):
    with ConfigMap(
        name="registry-cert-configmap",
        namespace=storage_ns.name,
        data=get_cert("registry_cert"),
    ) as configmap:
        create_dv_and_vm(
            "registry",
            "scratch-space-import-registry",
            storage_ns.name,
            f"{images_private_registry_server}:8443/{PRIVATE_REGISTRY_IMAGE}",
            configmap.name,
            ImportFromRegistryDataVolume.ContentType.KUBEVIRT,
            "5Gi",
        )


def get_file_url_http_server(get_images_external_http_server, file_name):
    return f"{get_images_external_http_server}cdi-test-images/cirros_images/{file_name}"


def get_file_url_http_server_basic_auth(get_images_external_http_server, file_name):
    return f"{get_images_external_http_server}mod-auth-basic/cirros_images/{file_name}"


def get_file_url_https_server(images_https_server, file_name):
    return f"{images_https_server}cdi-test-images/cirros_images/{file_name}"


def create_dv_and_vm_no_scratch_space(
    dv_name, namespace, url, cert_configmap, secret, content_type, size
):
    with ImportFromHttpDataVolume(
        name=dv_name,
        namespace=namespace,
        content_type=content_type,
        url=url,
        size=size,
        storage_class=py_config["storage_defaults"]["storage_class"],
        cert_configmap=cert_configmap,
        secret=secret,
    ) as dv:
        thread = threading.Thread(target=dv.wait())
        thread.daemon = True
        thread.start()
        pvc = PersistentVolumeClaim(name=f"{dv_name}-scratch", namespace=namespace)
        try:
            assert pvc.instance()
        except NotFoundError:
            pass
        storage_utils.create_vm_with_dv(dv)


def create_dv_and_vm(
    server_type, dv_name, namespace, url, configmap, content_type, size
):
    if server_type == "registry":
        with ImportFromRegistryDataVolume(
            name=dv_name,
            namespace=namespace,
            url=url,
            content_type=content_type,
            size=size,
            storage_class=py_config["storage_defaults"]["storage_class"],
            cert_configmap=configmap,
        ) as dv:
            verify_completeness(dv)
    elif server_type == "https":
        with ImportFromHttpDataVolume(
            name=dv_name,
            namespace=namespace,
            url=url,
            content_type=content_type,
            size=size,
            storage_class=py_config["storage_defaults"]["storage_class"],
            cert_configmap=configmap,
        ) as dv:
            verify_completeness(dv)


def verify_completeness(dv):
    pvc = PersistentVolumeClaim(name=f"{dv.name}-scratch", namespace=dv.namespace)
    pvc.wait_for_status(status=PersistentVolumeClaim.Status.BOUND, timeout=300)
    dv.wait()
    storage_utils.create_vm_with_dv(dv)
