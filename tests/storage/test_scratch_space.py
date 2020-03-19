# -*- coding: utf-8 -*-

import logging
import threading

import pytest
import utilities.storage
from openshift.dynamic.exceptions import NotFoundError
from resources.datavolume import DataVolume
from resources.persistent_volume_claim import PersistentVolumeClaim
from resources.secret import Secret
from resources.upload_token_request import UploadTokenRequest
from resources.utils import TimeoutSampler
from tests.storage import utils as storage_utils
from utilities.infra import (
    Images,
    get_images_external_http_server,
    get_images_https_server,
)


LOGGER = logging.getLogger(__name__)
PRIVATE_REGISTRY_IMAGE = "cirros-registry-disk-demo:latest"
ACCESS_KEY_ID = "cmVkaGF0"
SECRET_KEY = "MTIz"


@pytest.fixture()
def secret(namespace):
    with Secret(
        name="http-secret",
        namespace=namespace.name,
        accesskeyid=ACCESS_KEY_ID,
        secretkey=SECRET_KEY,
    ) as secret:
        yield secret


@pytest.mark.polarion("CNV-2327")
def test_upload_https_scratch_space_delete_pvc(
    skip_upstream, namespace, storage_class_matrix__module__, tmpdir
):
    local_name = f"{tmpdir}/{Images.Cirros.QCOW2_IMG}"
    remote_name = f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}"
    storage_utils.downloaded_image(remote_name=remote_name, local_name=local_name)
    storage_class = [*storage_class_matrix__module__][0]
    with utilities.storage.create_dv(
        source="upload",
        dv_name="scratch-space-upload-qcow2-https",
        namespace=namespace.name,
        size="3Gi",
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
    ) as dv:
        dv.scratch_pvc.wait_for_status(
            status=PersistentVolumeClaim.Status.BOUND, timeout=300
        )
        dv.scratch_pvc.delete()
        dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=180)
        with UploadTokenRequest(
            name="scratch-space-upload-qcow2-https",
            namespace=namespace.name,
            pvc_name=dv.pvc.name,
        ) as utr:
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
                    dv.wait_for_status(status=dv.Status.SUCCEEDED, timeout=300)
                    with storage_utils.create_vm_from_dv(dv=dv) as vm_dv:
                        storage_utils.check_disk_count_in_vm(vm_dv)
                    return True


@pytest.mark.polarion("CNV-2328")
def test_import_https_scratch_space_delete_pvc(
    skip_upstream, namespace, storage_class_matrix__module__, https_config_map
):
    storage_class = [*storage_class_matrix__module__][0]
    with storage_utils.create_dv(
        source="http",
        dv_name="scratch-space-import-qcow2-https",
        namespace=namespace.name,
        url=f"{get_images_https_server()}{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
        cert_configmap=https_config_map.name,
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
    ) as dv:
        dv.scratch_pvc.wait_for_status(
            status=PersistentVolumeClaim.Status.BOUND, timeout=300
        )
        dv.scratch_pvc.delete()
        dv.wait()
        with storage_utils.create_vm_from_dv(dv) as vm_dv:
            storage_utils.check_disk_count_in_vm(vm_dv)


@pytest.mark.parametrize(
    ("dv_name", "file_name", "content_type", "size"),
    [
        pytest.param(
            "no-scratch-space-import-raw-https",
            Images.Cirros.RAW_IMG,
            DataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
            id="cnv-2321-no-scratch-space-import-raw-https",
        ),
        pytest.param(
            "no-scratch-space-import-raw-gz-https",
            Images.Cirros.RAW_IMG_GZ,
            DataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
            id="cnv-2321-no-scratch-space-import-raw-gz-https",
        ),
        pytest.param(
            "no-scratch-space-import-raw-xz-https",
            Images.Cirros.RAW_IMG_XZ,
            DataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2321")),
            id="cnv-2321-no-scratch-space-import-raw-xz-https",
        ),
        pytest.param(
            "no-scratch-space-import-qcow2-https",
            Images.Cirros.QCOW2_IMG,
            DataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2324")),
            id="cnv-2321-no-scratch-space-import-qcow2-https",
        ),
    ],
)
def test_no_scratch_space_import_https_data_volume(
    skip_upstream,
    namespace,
    storage_class_matrix__module__,
    https_config_map,
    dv_name,
    file_name,
    content_type,
    size,
):
    storage_class = [*storage_class_matrix__module__][0]
    create_dv_and_vm_no_scratch_space(
        dv_name=dv_name,
        namespace=namespace.name,
        url=f"{get_images_https_server()}{Images.Cirros.DIR}/{file_name}",
        cert_configmap=https_config_map.name,
        content_type=content_type,
        size=size,
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
    )


@pytest.mark.parametrize(
    ("dv_name", "file_name"),
    [
        pytest.param(
            "scratch-space-import-qcow2-https",
            Images.Cirros.QCOW2_IMG,
            marks=(pytest.mark.polarion("CNV-2323")),
            id="cnv-2323-scratch-space-import-qcow2-https",
        ),
        pytest.param(
            "scratch-space-import-qcow2-gz-https",
            Images.Cirros.QCOW2_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2323")),
            id="cnv-2323-scratch-space-import-qcow2-gz-https",
        ),
        pytest.param(
            "scratch-space-import-qcow2-xz-https",
            Images.Cirros.QCOW2_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-2323")),
            id="cnv-2323-scratch-space-import-qcow2-xz-https",
        ),
    ],
)
def test_scratch_space_import_https_data_volume(
    skip_upstream,
    namespace,
    storage_class_matrix__module__,
    https_config_map,
    dv_name,
    file_name,
):
    storage_class = [*storage_class_matrix__module__][0]
    with utilities.storage.create_dv(
        source="http",
        dv_name=dv_name,
        namespace=namespace.name,
        url=f"{get_images_https_server()}{Images.Cirros.DIR}/{file_name}",
        cert_configmap=https_config_map.name,
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
    ) as dv:
        dv.scratch_pvc.wait_for_status(
            status=PersistentVolumeClaim.Status.BOUND, timeout=300
        )
        dv.wait()
        with storage_utils.create_vm_from_dv(dv) as vm_dv:
            storage_utils.check_disk_count_in_vm(vm_dv)


@pytest.mark.parametrize(
    ("dv_name", "file_name"),
    [
        pytest.param(
            "scratch-space-import-qcow2-gz-http",
            Images.Cirros.QCOW2_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2323")),
            id="cnv-2323-scratch-space-import-qcow2-gz-http",
        ),
        pytest.param(
            "scratch-space-import-qcow2-xz-http",
            Images.Cirros.QCOW2_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-2323")),
            id="cnv-2323-scratch-space-import-qcow2-xz-http",
        ),
    ],
)
def test_scratch_space_import_http_data_volume(
    skip_upstream, namespace, storage_class_matrix__module__, dv_name, file_name
):
    storage_class = [*storage_class_matrix__module__][0]
    with utilities.storage.create_dv(
        source="http",
        dv_name=dv_name,
        namespace=namespace.name,
        url=f"{get_images_external_http_server()}{Images.Cirros.DIR}/{file_name}",
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
    ) as dv:
        dv.scratch_pvc.wait_for_status(
            status=PersistentVolumeClaim.Status.BOUND, timeout=300
        )
        dv.wait()
        with storage_utils.create_vm_from_dv(dv) as vm_dv:
            storage_utils.check_disk_count_in_vm(vm_dv)


@pytest.mark.parametrize(
    ("dv_name", "file_name"),
    [
        pytest.param(
            "scratch-space-import-qcow2-gz-http-basic-auth",
            Images.Cirros.QCOW2_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2323")),
            id="cnv-2323-scratch-space-import-qcow2-gz-http-basic-auth",
        ),
        pytest.param(
            "scratch-space-import-qcow2xz-http-basic-auth",
            Images.Cirros.QCOW2_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-2323")),
            id="cnv-2323-scratch-space-import-qcow2-xz-http-basic-auth",
        ),
    ],
)
def test_scratch_space_import_http_basic_auth_data_volume(
    skip_upstream, namespace, storage_class_matrix__module__, secret, dv_name, file_name
):
    storage_class = [*storage_class_matrix__module__][0]
    with utilities.storage.create_dv(
        source="http",
        dv_name=dv_name,
        namespace=namespace.name,
        url=f"{get_images_external_http_server()}{Images.Cirros.MOD_AUTH_BASIC_DIR}/{file_name}",
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
        secret=secret,
    ) as dv:
        dv.scratch_pvc.wait_for_status(
            status=PersistentVolumeClaim.Status.BOUND, timeout=300
        )
        dv.wait()
        with storage_utils.create_vm_from_dv(dv) as vm_dv:
            storage_utils.check_disk_count_in_vm(vm_dv)


@pytest.mark.parametrize(
    ("dv_name", "file_name"),
    [
        pytest.param(
            "no-scratch-space-import-raw-http-basic-auth",
            Images.Cirros.RAW_IMG,
            marks=(pytest.mark.polarion("CNV-2321")),
            id="cnv-2321-no-scratch-space-import-raw-http-auth",
        ),
        pytest.param(
            "no-scratch-space-import-raw-gz-http-basic-auth",
            Images.Cirros.RAW_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2321")),
            id="cnv-2321-no-scratch-space-import-raw-gz-http-auth",
        ),
        pytest.param(
            "no-scratch-space-import-raw-xz-http-basic-auth",
            Images.Cirros.RAW_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-2321")),
            id="cnv-2321-no-scratch-space-import-raw-xz-http-auth",
        ),
        pytest.param(
            "no-scratch-space-import-qcow2-http-basic-auth",
            Images.Cirros.QCOW2_IMG,
            marks=(pytest.mark.polarion("CNV-2324")),
            id="cnv-2321-no-scratch-space-import-qcow2-http-auth",
        ),
    ],
)
def test_no_scratch_space_import_http_basic_auth(
    skip_upstream,
    namespace,
    storage_class_matrix__module__,
    secret,
    dv_name,
    file_name,
):
    storage_class = [*storage_class_matrix__module__][0]
    create_dv_and_vm_no_scratch_space(
        dv_name=dv_name,
        namespace=namespace.name,
        url=f"{get_images_external_http_server()}{Images.Cirros.MOD_AUTH_BASIC_DIR}/{file_name}",
        secret=secret,
        content_type=DataVolume.ContentType.KUBEVIRT,
        size="5Gi",
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
    )


@pytest.mark.parametrize(
    ("dv_name", "file_name"),
    [
        pytest.param(
            "no-scratch-space-import-raw-http",
            Images.Cirros.RAW_IMG,
            marks=(pytest.mark.polarion("CNV-2321")),
            id="cnv-2321-no-scratch-space-import-raw-http",
        ),
        pytest.param(
            "no-scratch-space-import-raw-gz-http",
            Images.Cirros.RAW_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2321")),
            id="cnv-2321-no-scratch-space-import-raw-gz-http",
        ),
        pytest.param(
            "no-scratch-space-import-raw-xz-http",
            Images.Cirros.RAW_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-2321")),
            id="cnv-2321-no-scratch-space-import-raw-xz-http",
        ),
    ],
)
def test_no_scratch_space_import_http(
    skip_upstream, namespace, storage_class_matrix__module__, dv_name, file_name,
):
    storage_class = [*storage_class_matrix__module__][0]
    create_dv_and_vm_no_scratch_space(
        dv_name=dv_name,
        namespace=namespace.name,
        url=f"{get_images_external_http_server()}{Images.Cirros.DIR}/{file_name}",
        content_type=DataVolume.ContentType.KUBEVIRT,
        size="5Gi",
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
    )


@pytest.mark.parametrize(
    ("file_name", "dv_name"),
    [
        pytest.param(
            Images.Cirros.QCOW2_IMG,
            "cnv-2315-scratch-space-upload-qcow2",
            marks=(pytest.mark.polarion("CNV-2315")),
            id="cnv-2315-scratch-space-upload-qcow2",
        ),
        pytest.param(
            Images.Cirros.QCOW2_IMG_GZ,
            "cnv-2315-scratch-space-upload-qcow2-gz",
            marks=(pytest.mark.polarion("CNV-2315")),
            id="cnv-2315-scratch-space-upload-qcow2-gz",
        ),
        pytest.param(
            Images.Cirros.QCOW2_IMG_XZ,
            "cnv-2315-scratch-space-upload-qcow2-xz",
            marks=(pytest.mark.polarion("CNV-2315")),
            id="cnv-2315-scratch-space-upload-qcow2-xz",
        ),
        pytest.param(
            Images.Cirros.RAW_IMG,
            "cnv-2315-scratch-space-upload-raw",
            marks=(pytest.mark.polarion("CNV-2315")),
            id="cnv-2315-scratch-space-upload-raw",
        ),
        pytest.param(
            Images.Cirros.RAW_IMG_XZ,
            "cnv-2315-scratch-space-upload-raw-xz",
            marks=(pytest.mark.polarion("CNV-2315")),
            id="cnv-2315-scratch-space-upload-raw-xz",
        ),
        pytest.param(
            Images.Cirros.RAW_IMG_GZ,
            "cnv-2315-scratch-space-upload-raw-gz",
            marks=(pytest.mark.polarion("CNV-2315")),
            id="cnv-2315-scratch-space-upload-raw-gz",
        ),
    ],
)
def test_scratch_space_upload_data_volume(
    skip_upstream, namespace, storage_class_matrix__module__, tmpdir, file_name, dv_name
):
    local_name = f"{tmpdir}/{file_name}"
    remote_name = f"{Images.Cirros.DIR}/{file_name}"
    storage_utils.downloaded_image(remote_name=remote_name, local_name=local_name)
    storage_class = [*storage_class_matrix__module__][0]
    with utilities.storage.create_dv(
        source="upload",
        dv_name=dv_name,
        namespace=namespace.name,
        size="3Gi",
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=180)
        with UploadTokenRequest(
            name="cnv-2315", namespace=namespace.name, pvc_name=dv.pvc.name
        ) as utr:
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
                    dv.scratch_pvc.wait_for_status(
                        status=PersistentVolumeClaim.Status.BOUND, timeout=300
                    )
                    dv.wait_for_status(status=dv.Status.SUCCEEDED, timeout=300)
                    with storage_utils.create_vm_from_dv(dv=dv) as vm_dv:
                        storage_utils.check_disk_count_in_vm(vm_dv)
                    return True


@pytest.mark.polarion("CNV-2319")
def test_scratch_space_import_registry_data_volume(
    skip_upstream,
    namespace,
    storage_class_matrix__module__,
    images_private_registry_server,
    registry_config_map,
):
    storage_class = [*storage_class_matrix__module__][0]
    with utilities.storage.create_dv(
        source="registry",
        dv_name="scratch-space-import-registry",
        namespace=namespace.name,
        url=f"{images_private_registry_server}:8443/{PRIVATE_REGISTRY_IMAGE}",
        cert_configmap=registry_config_map.name,
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
    ) as dv:
        dv.scratch_pvc.wait_for_status(
            status=PersistentVolumeClaim.Status.BOUND, timeout=300
        )
        dv.wait()
        with storage_utils.create_vm_from_dv(dv) as vm_dv:
            storage_utils.check_disk_count_in_vm(vm_dv)


def create_dv_and_vm_no_scratch_space(
    dv_name,
    namespace,
    storage_class,
    volume_mode,
    url,
    content_type,
    size,
    cert_configmap=None,
    secret=None,
):
    with utilities.storage.create_dv(
        source="http",
        dv_name=dv_name,
        namespace=namespace,
        content_type=content_type,
        url=url,
        cert_configmap=cert_configmap,
        size=size,
        secret=secret,
        storage_class=storage_class,
        volume_mode=volume_mode,
    ) as dv:
        thread = threading.Thread(target=dv.wait())
        thread.daemon = True
        thread.start()
        try:
            assert dv.scratch_pvc.instance()
        except NotFoundError:
            pass
        with storage_utils.create_vm_from_dv(dv=dv) as vm_dv:
            storage_utils.check_disk_count_in_vm(vm_dv)
