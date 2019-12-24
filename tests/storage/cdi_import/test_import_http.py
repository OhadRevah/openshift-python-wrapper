# -*- coding: utf-8 -*-

"""
Import from HTTP server
"""

import logging
import multiprocessing

import pytest
import utilities.storage
from openshift.dynamic.exceptions import UnprocessibleEntityError
from pytest_testconfig import config as py_config
from resources.configmap import ConfigMap
from resources.datavolume import DataVolume
from resources.utils import TimeoutExpiredError, TimeoutSampler
from tests.storage import utils
from utilities import console
from utilities.infra import BUG_STATUS_CLOSED, Images
from utilities.virt import CIRROS_IMAGE


LOGGER = logging.getLogger(__name__)

TEST_IMG_LOCATION = "cdi-test-images"
QCOW_IMG = "cirros-qcow2.img"
ISO_IMG = "Core-current.iso"
TAR_IMG = "archive.tar"


def get_file_url(url, file_name):
    return f"{url}{file_name}"


@pytest.mark.polarion("CNV-675")
def test_delete_pvc_after_successful_import(storage_ns, images_internal_http_server):
    url = get_file_url(images_internal_http_server["http"], QCOW_IMG)
    with utilities.storage.create_dv(
        source="http",
        dv_name="import-http-dv",
        namespace=storage_ns.name,
        url=url,
        size="500Mi",
        storage_class=py_config["default_storage_class"],
        volume_mode=py_config["default_volume_mode"],
    ) as dv:
        dv.wait_for_status(status=dv.Status.SUCCEEDED)
        pvc = dv.pvc
        pvc.delete()
        pvc.wait_for_status(status=pvc.Status.BOUND)
        dv.wait_for_status(status=dv.Status.IMPORT_SCHEDULED)
        dv.wait_for_status(status=dv.Status.SUCCEEDED)
        with utils.PodWithPVC(
            namespace=pvc.namespace,
            name=f"{dv.name}-pod",
            pvc_name=dv.name,
            volume_mode=py_config["default_volume_mode"],
        ) as pod:
            pod.wait_for_status(status=pod.Status.RUNNING)
            assert "disk.img" in pod.execute(command=["ls", "-1", "/pvc"])


@pytest.mark.polarion("CNV-876")
def test_invalid_url(storage_ns):
    # negative flow - invalid url
    with utilities.storage.create_dv(
        source="http",
        dv_name="import-http-dv-negative",
        namespace=storage_ns.name,
        url="https://noneexist.com",
        size="500Mi",
        storage_class=py_config["default_storage_class"],
        volume_mode=py_config["default_volume_mode"],
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.FAILED, timeout=300)


@pytest.mark.polarion("CNV-674")
def test_empty_url(storage_ns):
    with pytest.raises(UnprocessibleEntityError):
        with utilities.storage.create_dv(
            source="http",
            dv_name="import-http-dv",
            namespace=storage_ns.name,
            url="",
            size="500Mi",
            storage_class=py_config["default_storage_class"],
            volume_mode=py_config["default_volume_mode"],
        ):
            pass


@pytest.mark.polarion("CNV-2145")
def test_successful_import_archive(storage_ns, images_internal_http_server):
    url = get_file_url(images_internal_http_server["http"], TAR_IMG)
    with utilities.storage.create_dv(
        source="http",
        dv_name="import-http-dv",
        namespace=storage_ns.name,
        url=url,
        content_type=DataVolume.ContentType.ARCHIVE,
        size="500Mi",
        storage_class=py_config["default_storage_class"],
        volume_mode=DataVolume.VolumeMode.FILE,
    ) as dv:
        dv.wait()
        pvc = dv.pvc
        assert pvc.bound()
        with utils.PodWithPVC(
            namespace=pvc.namespace,
            name=f"{pvc.name}-pod",
            pvc_name=pvc.name,
            volume_mode=DataVolume.VolumeMode.FILE,
        ) as pod:
            pod.wait_for_status(status=pod.Status.RUNNING)
            assert pod.execute(command=["ls", "-1", "/pvc"]).count("\n") == 3


@pytest.mark.parametrize(
    "file_name",
    [
        pytest.param(QCOW_IMG, marks=(pytest.mark.polarion("CNV-2143"))),
        pytest.param(ISO_IMG, marks=(pytest.mark.polarion("CNV-377"))),
    ],
    ids=["import_qcow_image", "import_iso_image"],
)
def test_successful_import_image(storage_ns, images_internal_http_server, file_name):
    url = get_file_url(images_internal_http_server["http"], file_name)
    with utilities.storage.create_dv(
        source="http",
        dv_name="import-http-dv",
        namespace=storage_ns.name,
        url=url,
        size="500Mi",
        storage_class=py_config["default_storage_class"],
        volume_mode=py_config["default_volume_mode"],
    ) as dv:
        dv.wait()
        pvc = dv.pvc
        assert pvc.bound()
        with utils.PodWithPVC(
            namespace=pvc.namespace,
            name=f"{pvc.name}-pod",
            pvc_name=pvc.name,
            volume_mode=py_config["default_volume_mode"],
        ) as pod:
            pod.wait_for_status(status=pod.Status.RUNNING)
            assert "disk.img" in pod.execute(command=["ls", "-1", "/pvc"])


@pytest.mark.polarion("CNV-2338")
def test_successful_import_secure_archive(
    storage_ns, images_internal_http_server, internal_http_configmap
):
    url = get_file_url(images_internal_http_server["https"], TAR_IMG)
    with utilities.storage.create_dv(
        source="http",
        dv_name="import-https-dv",
        namespace=storage_ns.name,
        url=url,
        cert_configmap=internal_http_configmap.name,
        content_type=DataVolume.ContentType.ARCHIVE,
        size="500Mi",
        storage_class=py_config["default_storage_class"],
        volume_mode=DataVolume.VolumeMode.FILE,
    ) as dv:
        dv.wait_for_status(status=dv.Status.SUCCEEDED, timeout=300)
        pvc = dv.pvc
        assert pvc.bound()
        with utils.PodWithPVC(
            namespace=pvc.namespace,
            name=f"{pvc.name}-pod",
            pvc_name=pvc.name,
            volume_mode=DataVolume.VolumeMode.FILE,
        ) as pod:
            pod.wait_for_status(status=pod.Status.RUNNING)
            assert pod.execute(command=["ls", "-1", "/pvc"]).count("\n") == 3


@pytest.mark.polarion("CNV-2719")
def test_successful_import_secure_image(
    storage_ns, images_internal_http_server, internal_http_configmap
):
    url = get_file_url(images_internal_http_server["https"], QCOW_IMG)
    with utilities.storage.create_dv(
        source="http",
        dv_name="import-https-dv",
        namespace=storage_ns.name,
        url=url,
        cert_configmap=internal_http_configmap.name,
        size="500Mi",
        storage_class=py_config["default_storage_class"],
        volume_mode=py_config["default_volume_mode"],
    ) as dv:
        dv.wait_for_status(status=dv.Status.SUCCEEDED, timeout=300)
        pvc = dv.pvc
        assert pvc.bound()
        with utils.PodWithPVC(
            namespace=pvc.namespace,
            name=f"{pvc.name}-pod",
            pvc_name=pvc.name,
            volume_mode=py_config["default_volume_mode"],
        ) as pod:
            pod.wait_for_status(status=pod.Status.RUNNING)
            assert "disk.img" in pod.execute(command=["ls", "-1", "/pvc"])


@pytest.mark.parametrize(
    ("content_type", "file_name"),
    [
        pytest.param(
            DataVolume.ContentType.ARCHIVE,
            TAR_IMG,
            marks=(pytest.mark.polarion("CNV-2339")),
        ),
        pytest.param(
            DataVolume.ContentType.KUBEVIRT,
            Images.Cirros.RAW_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-784")),
        ),
    ],
    ids=["import_basic_auth_archive", "import_basic_auth_kubevirt"],
)
def test_successful_import_basic_auth(
    storage_ns,
    images_internal_http_server,
    internal_http_secret,
    content_type,
    file_name,
):
    if (
        content_type == DataVolume.ContentType.ARCHIVE
        and py_config["default_volume_mode"] == "Block"
    ):
        pytest.skip("Skipping test, can't use archives with volumeMode block")

    with utilities.storage.create_dv(
        source="http",
        dv_name="import-http-dv",
        namespace=storage_ns.name,
        url=get_file_url(images_internal_http_server["http_auth"], file_name),
        content_type=content_type,
        size="500Mi",
        secret=internal_http_secret,
        storage_class=py_config["default_storage_class"],
        volume_mode=py_config["default_volume_mode"],
    ) as dv:
        dv.wait()
        pvc = dv.pvc
        with utils.PodWithPVC(
            namespace=pvc.namespace,
            name=f"{pvc.name}-pod",
            pvc_name=pvc.name,
            volume_mode=py_config["default_volume_mode"],
        ) as pod:
            pod.wait_for_status(status=pod.Status.RUNNING)


@pytest.mark.polarion("CNV-2144")
def test_wrong_content_type(storage_ns, images_internal_http_server):
    with utilities.storage.create_dv(
        source="http",
        dv_name="import-http-dv",
        namespace=storage_ns.name,
        url=get_file_url(images_internal_http_server["http"], QCOW_IMG),
        content_type=DataVolume.ContentType.ARCHIVE,
        size="500Mi",
        storage_class=py_config["default_storage_class"],
        volume_mode=py_config["default_volume_mode"],
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.FAILED, timeout=300)


@pytest.mark.parametrize(
    ("dv_name", "file_name"),
    [
        pytest.param(
            "large-size",
            "invalid-qcow-large-size.img",
            marks=(
                pytest.mark.polarion("CNV-2553"),
                pytest.mark.bugzilla(
                    1739149, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
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
    with utilities.storage.create_dv(
        source="http",
        dv_name=dv_name,
        namespace=storage_ns.name,
        url=get_file_url(images_internal_http_server["http"], file_name),
        storage_class=py_config["default_storage_class"],
        volume_mode=py_config["default_volume_mode"],
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.FAILED, timeout=90)


@pytest.mark.parametrize(
    ("content_type", "file_name"),
    [
        pytest.param(
            DataVolume.ContentType.ARCHIVE,
            Images.Cirros.RAW_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-2220")),
        ),
        pytest.param(
            DataVolume.ContentType.ARCHIVE,
            Images.Cirros.RAW_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2701")),
        ),
    ],
    ids=["compressed_xz_archive_content_type", "compressed_gz_archive_content_type"],
)
# TODO: It's now a negative test but once https://jira.coreos.com/browse/CNV-1553 implement, here needs to be changed.
def test_unpack_compressed(
    storage_ns, images_internal_http_server, file_name, content_type
):
    with utilities.storage.create_dv(
        source="http",
        dv_name="unpack-compressed-dv",
        namespace=storage_ns.name,
        url=get_file_url(images_internal_http_server["http"], file_name),
        content_type=content_type,
        size="200Mi",
        storage_class=py_config["default_storage_class"],
        volume_mode=DataVolume.VolumeMode.FILE,
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.FAILED, timeout=300)


@pytest.mark.polarion("CNV-2811")
def test_certconfigmap(
    storage_ns, images_internal_http_server, internal_http_configmap
):
    with utilities.storage.create_dv(
        source="http",
        dv_name="cnv-2811",
        namespace=storage_ns.name,
        size="1Gi",
        storage_class=py_config["default_storage_class"],
        volume_mode=py_config["default_volume_mode"],
        url=get_file_url(url=images_internal_http_server["https"], file_name=QCOW_IMG),
        cert_configmap=internal_http_configmap.name,
    ) as dv:
        dv.wait()
        pvc = dv.pvc
        with utils.PodWithPVC(
            namespace=pvc.namespace,
            name=f"{pvc.name}-pod",
            pvc_name=pvc.name,
            volume_mode=py_config["default_volume_mode"],
        ) as pod:
            pod.wait_for_status(status="Running")
            assert pod.execute(command=["ls", "-1", "/pvc"]).count("\n") == 1


@pytest.mark.parametrize(
    ("name", "data"),
    [
        pytest.param(
            "cnv-2812",
            "-----BEGIN CERTIFICATE-----",
            marks=(pytest.mark.polarion("CNV-2812")),
        ),
        pytest.param("cnv-2813", None, marks=(pytest.mark.polarion("CNV-2813"))),
    ],
)
def test_certconfigmap_incorrect_cert(
    storage_ns, images_internal_http_server, name, data
):
    with ConfigMap(
        name="https-cert", namespace=storage_ns.name, cert_name="ca.pem", data=data
    ) as configmap:
        with utilities.storage.create_dv(
            source="http",
            dv_name=name,
            namespace=storage_ns.name,
            url=get_file_url(
                url=images_internal_http_server["https"], file_name=QCOW_IMG
            ),
            cert_configmap=configmap.name,
            size="1Gi",
            storage_class=py_config["default_storage_class"],
            volume_mode=py_config["default_volume_mode"],
        ) as dv:
            dv.wait_for_status(status=DataVolume.Status.FAILED, timeout=300)


@pytest.mark.polarion("CNV-2815")
def test_certconfigmap_missing_or_wrong_cm(storage_ns, images_internal_http_server):
    with utilities.storage.create_dv(
        source="http",
        dv_name="cnv-2815",
        namespace=storage_ns.name,
        url=get_file_url(url=images_internal_http_server["https"], file_name=QCOW_IMG),
        cert_configmap="wrong_name",
        size="1Gi",
        storage_class=py_config["default_storage_class"],
        volume_mode=py_config["default_volume_mode"],
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.IMPORT_SCHEDULED)
        with pytest.raises(TimeoutExpiredError):
            samples = TimeoutSampler(
                timeout=30,
                sleep=30,
                func=lambda: dv.status != DataVolume.Status.IMPORT_SCHEDULED,
            )
            for sample in samples:
                if sample:
                    LOGGER.error(
                        f"DV status is not as expected. \
                        Expected: {DataVolume.Status.IMPORT_SCHEDULED}. Found: {dv.status}"
                    )
                    raise AssertionError()


def blank_disk_import(storage_ns, dv_name):
    with utilities.storage.create_dv(
        source="blank",
        dv_name=dv_name,
        namespace=storage_ns.name,
        size="500Mi",
        storage_class=py_config["default_storage_class"],
        volume_mode=py_config["default_volume_mode"],
    ) as dv:
        dv.wait(timeout=180)
        with utils.create_vm_from_dv(
            dv=dv, image=CIRROS_IMAGE, vm_name=f"vm-{dv_name}"
        ) as vm_dv:
            utils.check_disk_count_in_vm(vm_dv)


@pytest.mark.polarion("CNV-2151")
def test_successful_blank_disk_import(storage_ns):
    with utilities.storage.create_dv(
        source="blank",
        dv_name="cnv-2151",
        namespace=storage_ns.name,
        size="500Mi",
        storage_class=py_config["default_storage_class"],
        volume_mode=py_config["default_volume_mode"],
    ) as dv:
        dv.wait()
        with utils.create_vm_from_dv(dv=dv, image=CIRROS_IMAGE) as vm_dv:
            utils.check_disk_count_in_vm(vm_dv)


@pytest.mark.polarion("CNV-2001")
def test_successful_concurrent_blank_disk_import(storage_ns):
    dv_processes = []
    for dv in range(4):
        dv_process = multiprocessing.Process(
            target=blank_disk_import, args=(storage_ns, f"dv-{dv}")
        )
        dv_process.start()
        dv_processes.append(dv_process)

    for dvs in dv_processes:
        dvs.join()
        if dvs.exitcode != 0:
            raise pytest.fail("Creating DV exited with non-zero return code")


@pytest.mark.parametrize(
    ("size", "unit", "expected_size"),
    [
        pytest.param("64", "Mi", "50", marks=(pytest.mark.polarion("CNV-1404"))),
        pytest.param("1", "Gi", "950", marks=(pytest.mark.polarion("CNV-1404"))),
        pytest.param("13", "Gi", "13", marks=(pytest.mark.polarion("CNV-1404"))),
    ],
)
@pytest.mark.skipif(
    py_config["default_volume_mode"] == "Block",
    reason="qemu-img reports 0 disk size for block",
)
def test_vmi_image_size(
    storage_ns,
    images_internal_http_server,
    internal_http_configmap,
    size,
    unit,
    expected_size,
):
    with utilities.storage.create_dv(
        source="http",
        dv_name="cnv-1404",
        namespace=storage_ns.name,
        size=f"{size}{unit}",
        storage_class=py_config["default_storage_class"],
        volume_mode=py_config["default_volume_mode"],
        url=get_file_url(url=images_internal_http_server["https"], file_name=QCOW_IMG),
        cert_configmap=internal_http_configmap.name,
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.SUCCEEDED, timeout=120)
        with utils.create_vm_from_dv(dv, image=CIRROS_IMAGE, start=False):
            with utils.PodWithPVC(
                namespace=dv.namespace,
                name=f"{dv.name}-pod",
                pvc_name=dv.name,
                volume_mode=py_config["default_volume_mode"],
            ) as pod:
                pod.wait_for_status(status=pod.Status.RUNNING)
                assert f"{expected_size}" <= pod.execute(
                    command=[
                        "bash",
                        "-c",
                        "qemu-img info /pvc/disk.img|grep 'disk size'|awk '{print $3}'|\
                        awk '{$0=substr($0,1,length($0)-1); print $0}'|tr -d '\n'",
                    ]
                )


@pytest.mark.polarion("CNV-3065")
def test_disk_falloc(storage_ns, images_internal_http_server, internal_http_configmap):
    with utilities.storage.create_dv(
        source="http",
        dv_name="cnv-3065",
        namespace=storage_ns.name,
        size="100Mi",
        storage_class=py_config["default_storage_class"],
        volume_mode=py_config["default_volume_mode"],
        url=get_file_url(url=images_internal_http_server["https"], file_name=QCOW_IMG),
        cert_configmap=internal_http_configmap.name,
    ) as dv:
        dv.wait()
        with utils.create_vm_from_dv(dv) as vm_dv:
            with console.Cirros(vm=vm_dv) as vm_console:
                LOGGER.info("Fill disk space.")
                vm_console.sendline("dd if=/dev/zero of=file bs=1M")
            vm_dv.restart(timeout=300, wait=True)
