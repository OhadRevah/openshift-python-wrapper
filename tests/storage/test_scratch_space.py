# -*- coding: utf-8 -*-

import logging
import threading

import pytest
from openshift.dynamic.exceptions import NotFoundError
from pytest_testconfig import config as py_config
from resources.datavolume import DataVolume
from resources.persistent_volume_claim import PersistentVolumeClaim
from resources.secret import Secret
from resources.upload_token_request import UploadTokenRequest
from resources.utils import TimeoutSampler
from tests.storage import utils as storage_utils
from tests.storage.utils import (
    CDI_IMAGES_DIR,
    CIRROS_IMAGES_DIR,
    get_file_url_https_server,
)
from utilities.infra import Images


LOGGER = logging.getLogger(__name__)

PRIVATE_REGISTRY_IMAGE = "cirros-registry-disk-demo:latest"


@pytest.mark.parametrize(
    ("dv_name", "file_name", "content_type", "size"),
    [
        pytest.param(
            "no-scratch-space-import-raw-https",
            Images.Cirros.RAW_IMG,
            DataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
        ),
        pytest.param(
            "no-scratch-space-import-raw-gz-https",
            Images.Cirros.RAW_IMG_GZ,
            DataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
        ),
        pytest.param(
            "no-scratch-space-import-raw-xz-https",
            Images.Cirros.RAW_IMG_XZ,
            DataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
        ),
        pytest.param(
            "no-scratch-space-import-qcow2-https",
            Images.Cirros.QCOW2_IMG,
            DataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2324")),
        ),
    ],
    ids=[
        "no-scratch-space-import-raw-https",
        "no-scratch-space-import-raw-gz-https",
        "no-scratch-space-import-raw-xz-https",
        "no-scratch-space-import-qcow2-https",
    ],
)
def test_no_scratch_space_import_https_data_volume(
    skip_upstream,
    storage_ns,
    images_https_server,
    https_config_map,
    dv_name,
    file_name,
    content_type,
    size,
):
    url = get_file_url_https_server(images_https_server, file_name)
    create_dv_and_vm_no_scratch_space(
        dv_name, storage_ns.name, url, https_config_map.name, None, content_type, size
    )


@pytest.mark.parametrize(
    ("dv_name", "file_name"),
    [
        pytest.param(
            "scratch-space-import-qcow2-https",
            Images.Cirros.QCOW2_IMG,
            marks=(pytest.mark.polarion("CNV-2323")),
        ),
        pytest.param(
            "scratch-space-import-qcow2gz-https",
            Images.Cirros.QCOW2_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2323")),
        ),
        pytest.param(
            "scratch-space-import-qcow2xz-https",
            Images.Cirros.QCOW2_IMG_XZ,
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
    skip_upstream, storage_ns, images_https_server, https_config_map, dv_name, file_name
):
    url = get_file_url_https_server(images_https_server, file_name)
    with storage_utils.create_dv(
        source="http",
        dv_name=dv_name,
        namespace=storage_ns.name,
        url=url,
        cert_configmap=https_config_map.name,
        storage_class=py_config["default_storage_class"],
    ) as dv:
        pvc = PersistentVolumeClaim(name=f"{dv.name}-scratch", namespace=dv.namespace)
        pvc.wait_for_status(status=PersistentVolumeClaim.Status.BOUND, timeout=300)
        dv.wait()
        with storage_utils.create_vm_from_dv(dv) as vm_dv:
            storage_utils.check_disk_count_in_vm(vm_dv)


@pytest.mark.parametrize(
    ("dv_name", "file_name", "content_type", "size"),
    [
        pytest.param(
            "no-scratch-space-import-raw-http-basic-auth",
            Images.Cirros.RAW_IMG,
            DataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
        ),
        pytest.param(
            "no-scratch-space-import-raw-gz-http-basic-auth",
            Images.Cirros.RAW_IMG_GZ,
            DataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
        ),
        pytest.param(
            "no-scratch-space-import-raw-xz-http-basic-auth",
            Images.Cirros.RAW_IMG_XZ,
            DataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
        ),
        pytest.param(
            "no-scratch-space-import-qcow2-http-basic-auth",
            Images.Cirros.QCOW2_IMG,
            DataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2324")),
        ),
    ],
    ids=[
        "no-scratch-space-import-raw-http-auth",
        "no-scratch-space-import-raw-gz-http-auth",
        "no-scratch-space-import-raw-xz-http-auth",
        "no-scratch-space-import-qcow2-http-auth",
    ],
)
def test_no_scratch_space_import_http_basic_auth(
    skip_upstream,
    storage_ns,
    images_external_http_server,
    dv_name,
    file_name,
    content_type,
    size,
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
            Images.Cirros.RAW_IMG,
            DataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
        ),
        pytest.param(
            "no-scratch-space-import-raw-gz-http",
            Images.Cirros.RAW_IMG_GZ,
            DataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
        ),
        pytest.param(
            "no-scratch-space-import-raw-xz-http",
            Images.Cirros.RAW_IMG_XZ,
            DataVolume.ContentType.KUBEVIRT,
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
    skip_upstream,
    storage_ns,
    images_external_http_server,
    dv_name,
    file_name,
    content_type,
    size,
):
    url = get_file_url_http_server(images_external_http_server, file_name)
    create_dv_and_vm_no_scratch_space(
        dv_name, storage_ns.name, url, None, None, content_type, size
    )


@pytest.mark.parametrize(
    ("file_name", "dv_name"),
    [
        pytest.param(
            Images.Cirros.QCOW2_IMG,
            "cnv-2315",
            marks=(pytest.mark.polarion("CNV-2315")),
        ),
        pytest.param(
            Images.Cirros.QCOW2_IMG_GZ,
            "cnv-2315",
            marks=(pytest.mark.polarion("CNV-2315")),
        ),
        pytest.param(
            Images.Cirros.QCOW2_IMG_XZ,
            "cnv-2315",
            marks=(pytest.mark.polarion("CNV-2315")),
        ),
        pytest.param(
            Images.Cirros.RAW_IMG, "cnv-2315", marks=(pytest.mark.polarion("CNV-2315"))
        ),
        pytest.param(
            Images.Cirros.RAW_IMG_XZ,
            "cnv-2315",
            marks=(pytest.mark.polarion("CNV-2315")),
        ),
        pytest.param(
            Images.Cirros.RAW_IMG_GZ,
            "cnv-2315",
            marks=(pytest.mark.polarion("CNV-2315")),
        ),
    ],
)
def test_scratch_space_upload_data_volume(
    skip_upstream, storage_ns, tmpdir, file_name, dv_name
):
    local_name = f"{tmpdir}/{file_name}"
    remote_name = f"{CDI_IMAGES_DIR}/{CIRROS_IMAGES_DIR}/{file_name}"
    storage_utils.downloaded_image(remote_name=remote_name, local_name=local_name)
    with storage_utils.create_dv(
        source="upload",
        dv_name=dv_name,
        namespace=storage_ns.name,
        size="3Gi",
        storage_class=py_config["default_storage_class"],
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=180)
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
                    with storage_utils.create_vm_from_dv(dv=dv) as vm_dv:
                        storage_utils.check_disk_count_in_vm(vm_dv)
                    return True


@pytest.mark.polarion("CNV-2319")
def test_scratch_space_import_registry_data_volume(
    skip_upstream, storage_ns, images_private_registry_server, registry_config_map
):
    with storage_utils.create_dv(
        source="registry",
        dv_name="scratch-space-import-registry",
        namespace=storage_ns.name,
        url=f"{images_private_registry_server}:8443/{PRIVATE_REGISTRY_IMAGE}",
        cert_configmap=registry_config_map.name,
        storage_class=py_config["default_storage_class"],
    ) as dv:
        pvc = PersistentVolumeClaim(name=f"{dv.name}-scratch", namespace=dv.namespace)
        pvc.wait_for_status(status=PersistentVolumeClaim.Status.BOUND, timeout=300)
        dv.wait()
        with storage_utils.create_vm_from_dv(dv) as vm_dv:
            storage_utils.check_disk_count_in_vm(vm_dv)


def get_file_url_http_server(get_images_external_http_server, file_name):
    return f"{get_images_external_http_server}cdi-test-images/cirros_images/{file_name}"


def get_file_url_http_server_basic_auth(get_images_external_http_server, file_name):
    return f"{get_images_external_http_server}mod-auth-basic/cirros_images/{file_name}"


def create_dv_and_vm_no_scratch_space(
    dv_name, namespace, url, cert_configmap, secret, content_type, size
):
    with storage_utils.create_dv(
        source="http",
        dv_name=dv_name,
        namespace=namespace,
        content_type=content_type,
        url=url,
        cert_configmap=cert_configmap,
        size=size,
        secret=secret,
        storage_class=py_config["default_storage_class"],
    ) as dv:
        thread = threading.Thread(target=dv.wait())
        thread.daemon = True
        thread.start()
        pvc = PersistentVolumeClaim(name=f"{dv_name}-scratch", namespace=namespace)
        try:
            assert pvc.instance()
        except NotFoundError:
            pass
        with storage_utils.create_vm_from_dv(dv=dv) as vm_dv:
            storage_utils.check_disk_count_in_vm(vm_dv)
