# -*- coding: utf-8 -*-

import pytest
import os
import logging
import threading

from pytest_testconfig import config as py_config
from resources.datavolume import ImportFromRegistryDataVolume, ImportFromHttpDataVolume
from resources.persistent_volume_claim import PersistentVolumeClaim
from resources.configmap import ConfigMap
from resources.secret import Secret
from tests.storage import utils as storage_utils
from openshift.dynamic.exceptions import NotFoundError
from resources.utils import TimeoutSampler
from resources.datavolume import UploadDataVolume
from resources.upload_token_request import UploadTokenRequest

LOGGER = logging.getLogger(__name__)
CDI_IMAGES_DIR = "cdi-test-images/cirros_images/"
PRIVATE_REGISTRY_IMAGE = "cirros-registry-disk-demo:latest"
RAW_IMAGE = "cirros-0.4.0-x86_64-disk.raw"
RAW_COMPRESSED_IMAGE = "cirros-0.4.0-x86_64-disk.raw.gz"
QCOW2_IMG = "cirros-0.4.0-x86_64-disk.qcow2"


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
            "no-scratch-space-import-raw-compressed-https",
            RAW_COMPRESSED_IMAGE,
            ImportFromHttpDataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
        ),
    ],
    ids=[
        "no-scratch-space-import-raw-https",
        "no-scratch-space-import-raw-compressed-https",
    ],
)
def test_no_scratch_space_import_https_data_volume(
    storage_ns, images_https_server, dv_name, file_name, content_type, size
):
    url = get_file_url_https_server(images_https_server, file_name)
    with ConfigMap(
        name="https-cert-configmap", namespace=storage_ns.name, data=get_cert("https")
    ) as configmap:
        create_dv_and_vm_no_scratch_space(
            dv_name, storage_ns.name, url, configmap.name, None, content_type, size
        )


@pytest.mark.polarion("CNV-2323")
def test_scratch_space_import_https_data_volume(storage_ns, images_https_server):
    url = get_file_url_https_server(images_https_server, QCOW2_IMG)
    with ConfigMap(
        name="https-cert-configmap", namespace=storage_ns.name, data=get_cert("https")
    ) as configmap:
        create_dv_and_vm(
            server_type="https",
            dv_name="scratch-space-import-https",
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
            "no-scratch-space-import-raw-compressed-http-basic-auth",
            RAW_COMPRESSED_IMAGE,
            ImportFromHttpDataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
        ),
    ],
    ids=[
        "no-scratch-space-import-raw-http-auth",
        "no-scratch-space-import-raw-compressed-http-auth",
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
            "no-scratch-space-import-raw-compressed-http",
            RAW_COMPRESSED_IMAGE,
            ImportFromHttpDataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
        ),
    ],
    ids=[
        "no-scratch-space-import-raw-http",
        "no-scratch-space-import-raw-compressed-http",
    ],
)
def test_no_scratch_space_import_http(
    storage_ns, images_external_http_server, dv_name, file_name, content_type, size
):
    url = get_file_url_http_server(images_external_http_server, file_name)
    create_dv_and_vm_no_scratch_space(
        dv_name, storage_ns.name, url, None, None, content_type, size
    )


@pytest.mark.polarion("CNV-2315")
def test_scratch_space_upload_data_volume(storage_ns, tmpdir):
    local_name = f"{tmpdir}/{QCOW2_IMG}"
    remote_name = f"{CDI_IMAGES_DIR}{QCOW2_IMG}"
    storage_utils.downloaded_image(remote_name=remote_name, local_name=local_name)
    with UploadDataVolume(
        name="cnv-2315",
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
                    dv.wait_for_status(status="Succeeded", timeout=300)
                    storage_utils.create_vm_with_dv(dv)
                    return True


@pytest.mark.polarion("CNV-2319")
def test_scratch_space_import_registry_data_volume(
    storage_ns, images_private_registry_server
):
    with ConfigMap(
        name="registry-cert-configmap",
        namespace=storage_ns.name,
        data=get_cert("registry"),
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


def get_cert(server_type):
    path = ""
    if server_type == "registry":
        path = os.path.join("tests/storage/cdi_import", "tlsregistry.crt")
    elif server_type == "https":
        path = os.path.join(
            "tests/storage/cdi_import", py_config[py_config["region"]]["https_cert"]
        )
    with open(path, "r") as cert_content:
        data = cert_content.read()
    return data


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
