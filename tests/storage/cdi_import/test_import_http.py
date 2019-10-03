# -*- coding: utf-8 -*-

"""
Import from HTTP server
"""

import pytest
from openshift.dynamic.exceptions import UnprocessibleEntityError
from pytest_testconfig import config as py_config
from resources.datavolume import ImportFromHttpDataVolume
from tests.storage import utils


QCOW_IMG = "cirros-qcow2.img"
ISO_IMG = "Core-current.iso"
TAR_IMG = "archive.tar"
COMPRESSED_XZ_FILE = "cirros-0.4.0-x86_64-disk.raw.xz"
COMPRESSED_GZ_FILE = "cirros-0.4.0-x86_64-disk.raw.gz"

CLOUD_INIT_USER_DATA = r"""
            #!/bin/sh
            echo 'printed from cloud-init userdata'"""


def get_file_url(url, file_name):
    return f"{url}{file_name}"


@pytest.mark.polarion("CNV-876")
def test_invalid_url(storage_ns):
    # negative flow - invalid url
    with ImportFromHttpDataVolume(
        name="import-http-dv-negative",
        namespace=storage_ns.name,
        content_type=ImportFromHttpDataVolume.ContentType.KUBEVIRT,
        url="https://noneexist.com",
        size="500Mi",
        storage_class=py_config["storage_defaults"]["storage_class"],
    ) as dv:
        dv.wait_for_status(status=ImportFromHttpDataVolume.Status.FAILED, timeout=300)


@pytest.mark.polarion("CNV-674")
def test_empty_url(storage_ns):
    with pytest.raises(UnprocessibleEntityError):
        with ImportFromHttpDataVolume(
            name="import-http-dv",
            namespace=storage_ns.name,
            content_type=ImportFromHttpDataVolume.ContentType.KUBEVIRT,
            url="",
            size="500Mi",
            storage_class=py_config["storage_defaults"]["storage_class"],
        ):
            pass


@pytest.mark.polarion("CNV-2145")
def test_successful_import_archive(storage_ns, images_internal_http_server):
    url = get_file_url(images_internal_http_server["http"], TAR_IMG)
    with ImportFromHttpDataVolume(
        name="import-http-dv",
        namespace=storage_ns.name,
        content_type=ImportFromHttpDataVolume.ContentType.ARCHIVE,
        url=url,
        size="500Mi",
        storage_class=py_config["storage_defaults"]["storage_class"],
    ) as dv:
        dv.wait()
        pvc = dv.pvc
        assert pvc.bound()
        with utils.PodWithPVC(
            namespace=pvc.namespace, name=f"{pvc.name}-pod", pvc_name=pvc.name
        ) as pod:
            pod.wait_for_status(status="Running")
            assert pod.execute(command=["ls", "-1", "/pvc"]).count("\n") == 3


@pytest.mark.parametrize(
    ("file_name"),
    [
        pytest.param(QCOW_IMG, marks=(pytest.mark.polarion("CNV-2143"))),
        pytest.param(ISO_IMG, marks=(pytest.mark.polarion("CNV-377"))),
    ],
    ids=["import_qcow_image", "import_iso_image"],
)
def test_successful_import_image(storage_ns, images_internal_http_server, file_name):
    url = get_file_url(images_internal_http_server["http"], file_name)
    with ImportFromHttpDataVolume(
        name="import-http-dv",
        namespace=storage_ns.name,
        content_type=ImportFromHttpDataVolume.ContentType.KUBEVIRT,
        url=url,
        size="500Mi",
        storage_class=py_config["storage_defaults"]["storage_class"],
    ) as dv:
        dv.wait()
        pvc = dv.pvc
        assert pvc.bound()
        with utils.PodWithPVC(
            namespace=pvc.namespace, name=f"{pvc.name}-pod", pvc_name=pvc.name
        ) as pod:
            pod.wait_for_status(status="Running")
            assert "disk.img" in pod.execute(command=["ls", "-1", "/pvc"])


@pytest.mark.polarion("CNV-2338")
def test_successful_import_secure_archive(
    storage_ns, images_internal_http_server, internal_http_configmap
):
    url = get_file_url(images_internal_http_server["https"], TAR_IMG)
    with ImportFromHttpDataVolume(
        name="import-https-dv",
        namespace=storage_ns.name,
        content_type=ImportFromHttpDataVolume.ContentType.ARCHIVE,
        url=url,
        size="500Mi",
        storage_class=py_config["storage_defaults"]["storage_class"],
        cert_configmap=internal_http_configmap.name,
    ) as dv:
        dv.wait_for_status(status="Succeeded", timeout=300)
        pvc = dv.pvc
        assert pvc.bound()
        with utils.PodWithPVC(
            namespace=pvc.namespace, name=f"{pvc.name}-pod", pvc_name=pvc.name
        ) as pod:
            pod.wait_for_status(status="Running")
            assert pod.execute(command=["ls", "-1", "/pvc"]).count("\n") == 3


@pytest.mark.polarion("CNV-2719")
def test_successful_import_secure_image(
    storage_ns, images_internal_http_server, internal_http_configmap
):
    url = get_file_url(images_internal_http_server["https"], QCOW_IMG)
    with ImportFromHttpDataVolume(
        name="import-https-dv",
        namespace=storage_ns.name,
        content_type=ImportFromHttpDataVolume.ContentType.KUBEVIRT,
        url=url,
        size="500Mi",
        storage_class=py_config["storage_defaults"]["storage_class"],
        cert_configmap=internal_http_configmap.name,
    ) as dv:
        dv.wait_for_status(status="Succeeded", timeout=300)
        pvc = dv.pvc
        assert pvc.bound()
        with utils.PodWithPVC(
            namespace=pvc.namespace, name=f"{pvc.name}-pod", pvc_name=pvc.name
        ) as pod:
            pod.wait_for_status(status="Running")
            assert "disk.img" in pod.execute(command=["ls", "-1", "/pvc"])


@pytest.mark.polarion("CNV-2339")
def test_successful_import_basic_auth(
    storage_ns, images_internal_http_server, internal_http_secret
):
    with ImportFromHttpDataVolume(
        name="import-http-dv",
        namespace=storage_ns.name,
        content_type=ImportFromHttpDataVolume.ContentType.ARCHIVE,
        url=get_file_url(images_internal_http_server["http_auth"], TAR_IMG),
        size="500Mi",
        storage_class=py_config["storage_defaults"]["storage_class"],
        secret=internal_http_secret.name,
    ) as dv:
        dv.wait()
        pvc = dv.pvc
        with utils.PodWithPVC(
            namespace=pvc.namespace, name=f"{pvc.name}-pod", pvc_name=pvc.name
        ) as pod:
            pod.wait_for_status(status="Running")


@pytest.mark.polarion("CNV-2144")
def test_wrong_content_type(storage_ns, images_internal_http_server):
    with ImportFromHttpDataVolume(
        name="import-http-dv",
        namespace=storage_ns.name,
        content_type=ImportFromHttpDataVolume.ContentType.ARCHIVE,
        url=get_file_url(images_internal_http_server["http"], QCOW_IMG),
        size="500Mi",
        storage_class=py_config["storage_defaults"]["storage_class"],
    ) as dv:
        dv.wait_for_status(status=ImportFromHttpDataVolume.Status.FAILED, timeout=300)


def create_vm_with_dv(ns_name, content_type, images_internal_http_server, sc):
    with ImportFromHttpDataVolume(
        name="import-http-dv-cirros",
        namespace=ns_name,
        content_type=content_type,
        url=get_file_url(images_internal_http_server["http"], QCOW_IMG),
        size="500Mi",
        storage_class=sc,
    ) as dv:
        dv.wait()
        utils.create_vm_with_dv(dv)


@pytest.mark.parametrize(
    "content_type",
    [
        pytest.param(
            ImportFromHttpDataVolume.ContentType.KUBEVIRT,
            marks=(pytest.mark.polarion("CNV-1865")),
        ),
        pytest.param(None, marks=(pytest.mark.polarion("CNV-1868"))),
    ],
)
def test_import_http_vm(storage_ns, images_internal_http_server, content_type):
    create_vm_with_dv(
        storage_ns.name,
        content_type,
        images_internal_http_server,
        py_config["storage_defaults"]["storage_class"],
    )


@pytest.mark.polarion("CNV-1909")
def test_default_storage_class(storage_ns, images_internal_http_server):
    create_vm_with_dv(storage_ns.name, None, images_internal_http_server, None)


@pytest.mark.parametrize(
    ("dv_name", "file_name"),
    [
        pytest.param(
            "large-size",
            "invalid-qcow-large-size.img",
            marks=(
                pytest.mark.polarion("CNV-2553"),
                pytest.mark.bugzilla(
                    1739149,
                    skip_when=lambda bug: bug.status not in ("VERIFIED", "ON_QA"),
                ),
            ),
        ),
        pytest.param(
            "large-json",
            "invalid-qcow-large-json.img",
            marks=(pytest.mark.polarion("CNV-2554")),
        ),
        pytest.param(
            "large-memory",
            "invalid-qcow-large-memory.img",
            marks=(pytest.mark.polarion("CNV-2255")),
        ),
        pytest.param(
            "backing-file",
            "invalid-qcow-backing-file.img",
            marks=(pytest.mark.polarion("CNV-2139")),
        ),
    ],
)
def test_import_invalid_qcow(
    storage_ns, images_internal_http_server, dv_name, file_name
):
    with ImportFromHttpDataVolume(
        name=dv_name,
        namespace=storage_ns.name,
        content_type=ImportFromHttpDataVolume.ContentType.KUBEVIRT,
        url=get_file_url(images_internal_http_server["http"], file_name),
        size="1Gi",
        storage_class=py_config["storage_defaults"]["storage_class"],
    ) as dv:
        dv.wait_for_status(status=ImportFromHttpDataVolume.Status.FAILED, timeout=90)


@pytest.mark.parametrize(
    ("content_type", "file_name"),
    [
        pytest.param(
            ImportFromHttpDataVolume.ContentType.ARCHIVE,
            COMPRESSED_XZ_FILE,
            marks=(pytest.mark.polarion("CNV-2220")),
        ),
        pytest.param(
            ImportFromHttpDataVolume.ContentType.ARCHIVE,
            COMPRESSED_GZ_FILE,
            marks=(pytest.mark.polarion("CNV-2701")),
        ),
    ],
    ids=["compressed_xz_archive_content_type", "compressed_gz_archive_content_type"],
)
# TODO: It's now a negative test but once https://jira.coreos.com/browse/CNV-1553 implement, here needs to be changed.
def test_unpack_compressed(
    storage_ns, images_internal_http_server, file_name, content_type
):
    with ImportFromHttpDataVolume(
        name="unpack-compressed-dv",
        namespace=storage_ns.name,
        content_type=content_type,
        url=get_file_url(images_internal_http_server["http"], file_name),
        size="200Mi",
        storage_class=py_config["storage_defaults"]["storage_class"],
    ) as dv:
        dv.wait_for_status(status=ImportFromHttpDataVolume.Status.FAILED, timeout=300)
