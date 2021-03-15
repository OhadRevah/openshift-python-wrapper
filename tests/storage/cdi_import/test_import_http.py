# -*- coding: utf-8 -*-

"""
Import from HTTP server
"""

import logging
import multiprocessing

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.pod import Pod
from ocp_resources.resource import Resource
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from openshift.dynamic.exceptions import UnprocessibleEntityError
from pytest_testconfig import config as py_config

import utilities.storage
from tests.storage import utils
from tests.storage.cdi_import.conftest import wait_for_importer_container_message
from tests.storage.utils import get_importer_pod
from utilities import console
from utilities.infra import BUG_STATUS_CLOSED, NON_EXIST_URL, Images, get_bug_status
from utilities.storage import ErrorMsg, PodWithPVC, create_dummy_first_consumer_pod
from utilities.virt import CIRROS_IMAGE, validate_vmi_ga_info_vs_windows_os_info


LOGGER = logging.getLogger(__name__)

ISO_IMG = "Core-current.iso"
TAR_IMG = "archive.tar"


def get_file_url(url, file_name):
    return f"{url}{file_name}"


@pytest.fixture()
def dv_with_annotation(skip_upstream, admin_client, namespace, linux_nad):
    with utilities.storage.create_dv(
        source="http",
        dv_name="dv-annotation",
        namespace=namespace.name,
        url=f"{utilities.storage.get_images_external_http_server()}{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
        volume_mode=py_config["default_volume_mode"],
        storage_class=py_config["default_storage_class"],
        multus_annotation=linux_nad.name,
    ) as dv:
        dv.wait_for_status(
            status=DataVolume.Status.IMPORT_IN_PROGRESS,
            timeout=60,
            stop_status=DataVolume.Status.SUCCEEDED,
        )
        importer_pod = get_importer_pod(dyn_client=admin_client, namespace=dv.namespace)
        return importer_pod.instance.metadata.annotations


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "import-http-dv",
                "source": "http",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": "500Mi",
            },
            marks=pytest.mark.polarion("CNV-675"),
        ),
    ],
    indirect=True,
)
@pytest.mark.polarion("CNV-675")
def test_delete_pvc_after_successful_import(data_volume_multi_storage_scope_function):
    pvc = data_volume_multi_storage_scope_function.pvc
    pvc.delete()
    create_dummy_first_consumer_pod(pvc=pvc)
    data_volume_multi_storage_scope_function.wait_for_status(
        status=data_volume_multi_storage_scope_function.Status.IMPORT_SCHEDULED
    )
    data_volume_multi_storage_scope_function.wait_for_status(
        status=data_volume_multi_storage_scope_function.Status.SUCCEEDED
    )
    with PodWithPVC(
        namespace=pvc.namespace,
        name=f"{data_volume_multi_storage_scope_function.name}-pod",
        pvc_name=data_volume_multi_storage_scope_function.name,
        volume_mode=data_volume_multi_storage_scope_function.volume_mode,
    ) as pod:
        pod.wait_for_status(status=pod.Status.RUNNING)
        assert "disk.img" in pod.execute(command=["ls", "-1", "/pvc"])


@pytest.mark.polarion("CNV-876")
def test_invalid_url(namespace, storage_class_matrix__module__):
    # negative flow - invalid url
    storage_class = [*storage_class_matrix__module__][0]
    with utilities.storage.create_dv(
        source="http",
        dv_name="import-http-dv-negative",
        namespace=namespace.name,
        url=NON_EXIST_URL,
        size="500Mi",
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
    ) as dv:
        dv.wait_for_condition(
            condition=DataVolume.Condition.Type.BOUND,
            status=DataVolume.Condition.Status.TRUE,
            timeout=300,
        )
        dv.wait_for_status(
            status=DataVolume.Status.IMPORT_IN_PROGRESS,
            timeout=300,
            stop_status=DataVolume.Status.SUCCEEDED,
        )
        dv.wait_for_condition(
            condition=DataVolume.Condition.Type.READY,
            status=DataVolume.Condition.Status.FALSE,
            timeout=300,
        )


@pytest.mark.polarion("CNV-674")
def test_empty_url(namespace, storage_class_matrix__module__):
    storage_class = [*storage_class_matrix__module__][0]
    with pytest.raises(UnprocessibleEntityError):
        with utilities.storage.create_dv(
            source="http",
            dv_name="import-http-dv",
            namespace=namespace.name,
            url="",
            size="500Mi",
            storage_class=storage_class,
            volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
        ):
            pass


@pytest.mark.polarion("CNV-2145")
def test_successful_import_archive(
    namespace,
    storage_class_matrix__module__,
    images_internal_http_server,
    skip_block_volumemode_scope_module,
):
    """"Skip block volume mode - archive does not support block mode DVs,\
        https://github.com/kubevirt/containerized-data-importer/blob/master/doc/supported_operations.md"""

    url = get_file_url(url=images_internal_http_server["http"], file_name=TAR_IMG)
    with utilities.storage.create_dv(
        source="http",
        dv_name="import-http-dv",
        namespace=namespace.name,
        url=url,
        content_type=DataVolume.ContentType.ARCHIVE,
        size="500Mi",
        **utils.storage_params(storage_class_matrix=storage_class_matrix__module__),
    ) as dv:
        dv.wait()
        pvc = dv.pvc
        assert pvc.bound()
        with PodWithPVC(
            namespace=pvc.namespace,
            name=f"{pvc.name}-pod",
            pvc_name=pvc.name,
            volume_mode=dv.volume_mode,
        ) as pod:
            pod.wait_for_status(status=pod.Status.RUNNING)
            assert pod.execute(command=["ls", "-1", "/pvc"]).count("\n") == 3


@pytest.mark.parametrize(
    "file_name",
    [
        pytest.param(Images.Cdi.QCOW2_IMG, marks=(pytest.mark.polarion("CNV-2143"))),
        pytest.param(ISO_IMG, marks=(pytest.mark.polarion("CNV-377"))),
    ],
    ids=["import_qcow_image", "import_iso_image"],
)
def test_successful_import_image(
    namespace, storage_class_matrix__module__, images_internal_http_server, file_name
):
    url = get_file_url(url=images_internal_http_server["http"], file_name=file_name)
    storage_class = [*storage_class_matrix__module__][0]
    with utilities.storage.create_dv(
        source="http",
        dv_name="import-http-dv",
        namespace=namespace.name,
        url=url,
        size="500Mi",
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
    ) as dv:
        dv.wait()
        pvc = dv.pvc
        assert pvc.bound()
        with PodWithPVC(
            namespace=pvc.namespace,
            name=f"{pvc.name}-pod",
            pvc_name=pvc.name,
            volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
        ) as pod:
            pod.wait_for_status(status=pod.Status.RUNNING)
            assert "disk.img" in pod.execute(command=["ls", "-1", "/pvc"])


@pytest.mark.polarion("CNV-2338")
def test_successful_import_secure_archive(
    namespace,
    storage_class_matrix__module__,
    images_internal_http_server,
    internal_http_configmap,
    skip_block_volumemode_scope_module,
):
    """"Skip block volume mode - archive does not support block mode DVs,\
        https://github.com/kubevirt/containerized-data-importer/blob/master/doc/supported_operations.md"""

    url = get_file_url(url=images_internal_http_server["https"], file_name=TAR_IMG)
    with utilities.storage.create_dv(
        source="http",
        dv_name="import-https-dv",
        namespace=namespace.name,
        url=url,
        cert_configmap=internal_http_configmap.name,
        content_type=DataVolume.ContentType.ARCHIVE,
        size="500Mi",
        **utils.storage_params(storage_class_matrix=storage_class_matrix__module__),
    ) as dv:
        dv.wait_for_status(status=dv.Status.SUCCEEDED, timeout=300)
        pvc = dv.pvc
        assert pvc.bound()
        with PodWithPVC(
            namespace=pvc.namespace,
            name=f"{pvc.name}-pod",
            pvc_name=pvc.name,
            volume_mode=dv.volume_mode,
        ) as pod:
            pod.wait_for_status(status=pod.Status.RUNNING)
            assert pod.execute(command=["ls", "-1", "/pvc"]).count("\n") == 3


@pytest.mark.polarion("CNV-2719")
def test_successful_import_secure_image(
    namespace,
    storage_class_matrix__module__,
    images_internal_http_server,
    internal_http_configmap,
):
    url = get_file_url(
        url=images_internal_http_server["https"], file_name=Images.Cdi.QCOW2_IMG
    )
    storage_class = [*storage_class_matrix__module__][0]
    with utilities.storage.create_dv(
        source="http",
        dv_name="import-https-dv",
        namespace=namespace.name,
        url=url,
        cert_configmap=internal_http_configmap.name,
        size="500Mi",
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
    ) as dv:
        dv.wait_for_status(status=dv.Status.SUCCEEDED, timeout=300)
        pvc = dv.pvc
        assert pvc.bound()
        with PodWithPVC(
            namespace=pvc.namespace,
            name=f"{pvc.name}-pod",
            pvc_name=pvc.name,
            volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
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
    namespace,
    storage_class_matrix__module__,
    images_internal_http_server,
    internal_http_secret,
    content_type,
    file_name,
):
    storage_class = [*storage_class_matrix__module__][0]
    if (
        content_type == DataVolume.ContentType.ARCHIVE
        and storage_class_matrix__module__[storage_class]["volume_mode"] == "Block"
    ):
        pytest.skip("Skipping test, can't use archives with volumeMode block")

    with utilities.storage.create_dv(
        source="http",
        dv_name="import-http-dv",
        namespace=namespace.name,
        url=get_file_url(
            url=images_internal_http_server["http_auth"], file_name=file_name
        ),
        content_type=content_type,
        size="500Mi",
        secret=internal_http_secret,
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
    ) as dv:
        dv.wait()
        pvc = dv.pvc
        with PodWithPVC(
            namespace=pvc.namespace,
            name=f"{pvc.name}-pod",
            pvc_name=pvc.name,
            volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
        ) as pod:
            pod.wait_for_status(status=pod.Status.RUNNING)


@pytest.mark.polarion("CNV-2144")
def test_wrong_content_type(
    admin_client,
    namespace,
    storage_class_matrix__module__,
    images_internal_http_server,
):
    storage_class = [*storage_class_matrix__module__][0]
    with utilities.storage.create_dv(
        source="http",
        dv_name="import-http-dv",
        namespace=namespace.name,
        url=get_file_url(
            url=images_internal_http_server["http"], file_name=Images.Cdi.QCOW2_IMG
        ),
        content_type=DataVolume.ContentType.ARCHIVE,
        size="500Mi",
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
    ) as dv:
        dv.wait_for_status(
            status=DataVolume.Status.IMPORT_IN_PROGRESS,
            timeout=60,
            stop_status=DataVolume.Status.SUCCEEDED,
        )
        importer_pod = get_importer_pod(dyn_client=admin_client, namespace=dv.namespace)
        wait_for_importer_container_message(
            importer_pod=importer_pod, msg=ErrorMsg.EXIT_STATUS_2
        )


@pytest.mark.parametrize(
    ("dv_name", "file_name", "error_message"),
    [
        pytest.param(
            "large-size",
            "invalid-qcow-large-size.img",
            ErrorMsg.INVALID_FORMAT_FOR_QCOW,
            marks=(
                pytest.mark.polarion("CNV-2553"),
                pytest.mark.bugzilla(
                    1827793,
                    skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED,
                ),
            ),
        ),
        pytest.param(
            "large-json",
            "invalid-qcow-large-json.img",
            ErrorMsg.REQUESTED_RANGE_NOT_SATISFIABLE,
            marks=(pytest.mark.polarion("CNV-2554"),),
        ),
        pytest.param(
            "large-memory",
            "invalid-qcow-large-memory.img",
            ErrorMsg.COULD_NOT_OPEN_SIZE_TOO_BIG,
            marks=(pytest.mark.polarion("CNV-2555"),),
        ),
        pytest.param(
            "backing-file",
            "invalid-qcow-backing-file.img",
            ErrorMsg.COULD_NOT_OPEN_SIZE_TOO_BIG,
            marks=(pytest.mark.polarion("CNV-2139"),),
        ),
    ],
)
def test_import_invalid_qcow(
    admin_client,
    namespace,
    storage_class_matrix__module__,
    images_internal_http_server,
    dv_name,
    file_name,
    error_message,
    bugzilla_connection_params,
):
    # TODO: remove once bug #1850501 is fixed
    if [*storage_class_matrix__module__][
        0
    ] == "ocs-storagecluster-ceph-rbd" and dv_name in ("backing-file", "large-memory"):
        if (
            get_bug_status(
                bugzilla_connection_params=bugzilla_connection_params, bug=1850501
            )
            not in BUG_STATUS_CLOSED
        ):
            pytest.skip(msg="Skipping test on OCS due to bug #1850501")

    with utilities.storage.create_dv(
        source="http",
        dv_name=dv_name,
        namespace=namespace.name,
        url=get_file_url(url=images_internal_http_server["http"], file_name=file_name),
        **utils.storage_params(storage_class_matrix=storage_class_matrix__module__),
    ) as dv:
        dv.wait_for_status(
            status=DataVolume.Status.IMPORT_IN_PROGRESS,
            timeout=60,
            stop_status=DataVolume.Status.SUCCEEDED,
        )
        importer_pod = get_importer_pod(dyn_client=admin_client, namespace=dv.namespace)
        wait_for_importer_container_message(
            importer_pod=importer_pod, msg=error_message
        )


@pytest.mark.parametrize(
    ("content_type", "file_name"),
    [
        pytest.param(
            DataVolume.ContentType.ARCHIVE,
            Images.Cirros.RAW_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-2220")),
            id="compressed_xz_archive_content_type",
        ),
        pytest.param(
            DataVolume.ContentType.ARCHIVE,
            Images.Cirros.RAW_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2701")),
            id="compressed_gz_archive_content_type",
        ),
    ],
)
# TODO: It's now a negative test but once https://jira.coreos.com/browse/CNV-1553 implement, here needs to be changed.
def test_unpack_compressed(
    admin_client,
    namespace,
    storage_class_matrix__module__,
    images_internal_http_server,
    file_name,
    content_type,
):
    storage_class = [*storage_class_matrix__module__][0]
    with utilities.storage.create_dv(
        source="http",
        dv_name="unpack-compressed-dv",
        namespace=namespace.name,
        url=get_file_url(url=images_internal_http_server["http"], file_name=file_name),
        content_type=content_type,
        size="200Mi",
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
    ) as dv:
        dv.wait_for_status(
            status=DataVolume.Status.IMPORT_IN_PROGRESS,
            timeout=60,
            stop_status=DataVolume.Status.SUCCEEDED,
        )
        importer_pod = get_importer_pod(dyn_client=admin_client, namespace=dv.namespace)
        wait_for_importer_container_message(
            importer_pod=importer_pod, msg=ErrorMsg.EXIT_STATUS_2
        )


@pytest.mark.polarion("CNV-2811")
def test_certconfigmap(
    namespace,
    storage_class_matrix__module__,
    images_internal_http_server,
    internal_http_configmap,
):
    storage_class = [*storage_class_matrix__module__][0]
    with utilities.storage.create_dv(
        source="http",
        dv_name="cnv-2811",
        namespace=namespace.name,
        size="1Gi",
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
        url=get_file_url(
            url=images_internal_http_server["https"], file_name=Images.Cdi.QCOW2_IMG
        ),
        cert_configmap=internal_http_configmap.name,
    ) as dv:
        dv.wait()
        pvc = dv.pvc
        with PodWithPVC(
            namespace=pvc.namespace,
            name=f"{pvc.name}-pod",
            pvc_name=pvc.name,
            volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
        ) as pod:
            pod.wait_for_status(status=pod.Status.RUNNING)
            assert pod.execute(command=["ls", "-1", "/pvc"]).count("\n") == 1


@pytest.mark.parametrize(
    ("name", "https_config_map"),
    [
        pytest.param(
            "cnv-2812",
            {"data": "-----BEGIN CERTIFICATE-----"},
            marks=(pytest.mark.polarion("CNV-2812")),
        ),
        pytest.param(
            "cnv-2813", {"data": None}, marks=(pytest.mark.polarion("CNV-2813"))
        ),
    ],
    indirect=["https_config_map"],
)
def test_certconfigmap_incorrect_cert(
    admin_client,
    namespace,
    storage_class_matrix__module__,
    images_internal_http_server,
    name,
    https_config_map,
):
    storage_class = [*storage_class_matrix__module__][0]
    with utilities.storage.create_dv(
        source="http",
        dv_name=name,
        namespace=namespace.name,
        url=get_file_url(
            url=images_internal_http_server["https"], file_name=Images.Cdi.QCOW2_IMG
        ),
        cert_configmap=https_config_map.name,
        size="1Gi",
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
    ) as dv:
        dv.wait_for_status(
            status=DataVolume.Status.IMPORT_IN_PROGRESS,
            timeout=60,
            stop_status=DataVolume.Status.SUCCEEDED,
        )
        importer_pod = get_importer_pod(dyn_client=admin_client, namespace=dv.namespace)
        wait_for_importer_container_message(
            importer_pod=importer_pod,
            msg=ErrorMsg.CERTIFICATE_SIGNED_UNKNOWN_AUTHORITY,
        )


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cnv-2815",
                "source": "http",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": "1Gi",
                "cert_configmap": "wrong_name",
                "wait": False,
            },
            marks=pytest.mark.polarion("CNV-2815"),
        ),
    ],
    indirect=True,
)
@pytest.mark.polarion("CNV-2815")
def test_certconfigmap_missing_or_wrong_cm(data_volume_multi_storage_scope_function):
    with pytest.raises(TimeoutExpiredError):
        samples = TimeoutSampler(
            wait_timeout=60,
            sleep=10,
            func=lambda: data_volume_multi_storage_scope_function.status
            != DataVolume.Status.IMPORT_SCHEDULED,
        )
        for sample in samples:
            if sample:
                LOGGER.error(
                    f"DV status is not as expected."
                    f"Expected: {DataVolume.Status.IMPORT_SCHEDULED}. "
                    f"Found: {data_volume_multi_storage_scope_function.status}"
                )


def blank_disk_import(namespace, storage_params, dv_name):
    with utilities.storage.create_dv(
        source="blank",
        dv_name=dv_name,
        namespace=namespace.name,
        size="100Mi",
        **utils.storage_params(storage_class_matrix=storage_params),
    ) as dv:
        dv.wait_for_condition(
            condition=DataVolume.Condition.Type.BOUND,
            status=DataVolume.Condition.Status.TRUE,
            timeout=60,
        )
        dv.wait_for_condition(
            condition=DataVolume.Condition.Type.READY,
            status=DataVolume.Condition.Status.TRUE,
            timeout=60,
        )
        with utils.create_vm_from_dv(
            dv=dv, image=CIRROS_IMAGE, vm_name=f"vm-{dv_name}"
        ) as vm_dv:
            utils.check_disk_count_in_vm(vm=vm_dv)


@pytest.mark.parametrize(
    "number_of_threads",
    [
        pytest.param(
            1,
            marks=(pytest.mark.polarion("CNV-2151")),
        ),
        pytest.param(
            4,
            marks=(pytest.mark.polarion("CNV-2001")),
        ),
    ],
)
def test_successful_concurrent_blank_disk_import(
    namespace,
    storage_class_matrix__module__,
    number_of_threads,
):
    dv_processes = []
    for dv in range(number_of_threads):
        dv_process = multiprocessing.Process(
            target=blank_disk_import,
            args=(namespace, storage_class_matrix__module__, f"dv{dv}"),
        )
        dv_process.start()
        dv_processes.append(dv_process)

    for dvs in dv_processes:
        dvs.join()
        assert dvs.exitcode == 0, "Creating DV exited with non-zero return code"


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [{"dv_name": "cnv-2004", "source": "blank", "image": "", "dv_size": "500Mi"}],
    indirect=True,
)
@pytest.mark.polarion("CNV-2004")
def test_blank_disk_import_validate_status(data_volume_multi_storage_scope_function):
    data_volume_multi_storage_scope_function.wait_for_status(
        status=DataVolume.Status.SUCCEEDED, timeout=300
    )


@pytest.mark.parametrize(
    ("size", "unit", "expected_size"),
    [
        pytest.param("64", "Mi", "64M", marks=(pytest.mark.polarion("CNV-1404"))),
        pytest.param("1", "Gi", "1.0G", marks=(pytest.mark.polarion("CNV-1404"))),
        pytest.param("13", "Gi", "13G", marks=(pytest.mark.polarion("CNV-1404"))),
    ],
)
def test_vmi_image_size(
    namespace,
    storage_class_matrix__module__,
    images_internal_http_server,
    internal_http_configmap,
    size,
    unit,
    expected_size,
):
    storage_class = [*storage_class_matrix__module__][0]
    with utilities.storage.create_dv(
        source="http",
        dv_name="cnv-1404",
        namespace=namespace.name,
        size=f"{size}{unit}",
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
        url=get_file_url(
            url=images_internal_http_server["https"], file_name=Images.Cdi.QCOW2_IMG
        ),
        cert_configmap=internal_http_configmap.name,
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.SUCCEEDED, timeout=240)
        with utils.create_vm_from_dv(dv=dv, image=CIRROS_IMAGE, start=False):
            with PodWithPVC(
                namespace=dv.namespace,
                name=f"{dv.name}-pod",
                pvc_name=dv.name,
                volume_mode=storage_class_matrix__module__[storage_class][
                    "volume_mode"
                ],
            ) as pod:
                pod.wait_for_status(status=pod.Status.RUNNING)
                assert f"{expected_size}" <= pod.execute(
                    command=[
                        "bash",
                        "-c",
                        "qemu-img info /pvc/disk.img|grep 'virtual size'|awk '{print $3}'|tr -d '\n'",
                    ]
                )


@pytest.mark.polarion("CNV-3065")
def test_disk_falloc(
    namespace,
    storage_class_matrix__module__,
    images_internal_http_server,
    internal_http_configmap,
):
    storage_class = [*storage_class_matrix__module__][0]
    with utilities.storage.create_dv(
        source="http",
        dv_name="cnv-3065",
        namespace=namespace.name,
        size="100Mi",
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
        url=get_file_url(
            url=images_internal_http_server["https"], file_name=Images.Cdi.QCOW2_IMG
        ),
        cert_configmap=internal_http_configmap.name,
    ) as dv:
        dv.wait()
        with utils.create_vm_from_dv(dv=dv) as vm_dv:
            with console.Cirros(vm=vm_dv) as vm_console:
                LOGGER.info("Fill disk space.")
                vm_console.sendline("dd if=/dev/zero of=file bs=1M")
                vm_console.expect(
                    "dd: writing 'file': No space left on device", timeout=60
                )


@pytest.mark.destructive
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cnv-3362",
                "source": "http",
                "image": f"{Images.Rhel.DIR}/{Images.Rhel.RHEL8_2_IMG}",
                "dv_size": "25Gi",
                "access_modes": DataVolume.AccessMode.RWX,
                "wait": False,
            },
            marks=pytest.mark.polarion("CNV-3632"),
        ),
    ],
    indirect=True,
)
def test_vm_from_dv_on_different_node(
    admin_client,
    skip_when_one_node,
    skip_access_mode_rwo_scope_function,
    skip_non_shared_storage,
    schedulable_nodes,
    data_volume_multi_storage_scope_function,
):
    """
    Test that create and run VM from DataVolume (only use RWX access mode) on different node.
    It applies to shared storage like Ceph or NFS. It cannot be tested on local storage like HPP.
    """
    data_volume_multi_storage_scope_function.pvc.wait_for_status(
        status=PersistentVolumeClaim.Status.BOUND, timeout=30
    )
    importer_pod = get_importer_pod(
        dyn_client=admin_client,
        namespace=data_volume_multi_storage_scope_function.namespace,
    )
    importer_node_name = importer_pod.node.name
    importer_pod.wait_for_status(status=Pod.Status.RUNNING, timeout=30)
    nodes = list(
        filter(lambda node: importer_pod.node.name != node.name, schedulable_nodes)
    )
    data_volume_multi_storage_scope_function.wait_for_status(
        status=DataVolume.Status.SUCCEEDED, timeout=720
    )
    with utils.create_vm_from_dv(
        dv=data_volume_multi_storage_scope_function,
        vm_name=Images.Rhel.RHEL8_2_IMG,
        node_selector=nodes[0].name,
    ) as vm_dv:
        assert vm_dv.vmi.node.name != importer_node_name


@pytest.mark.tier3
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function,"
    "vm_instance_from_template_multi_storage_scope_function,"
    "started_windows_vm",
    [
        pytest.param(
            {
                "dv_name": "dv-win-19",
                "source": "http",
                "image": f"{Images.Windows.RAW_DIR}/{Images.Windows.WIN19_RAW}",
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            },
            {
                "vm_name": f"vm-win-{py_config['latest_windows_os_dict']['os_version']}",
                "template_labels": py_config["latest_windows_os_dict"][
                    "template_labels"
                ],
                "cpu_threads": 2,
                "ssh": True,
                "username": py_config["windows_username"],
                "password": py_config["windows_password"],
            },
            {"os_version": py_config["latest_windows_os_dict"]["os_version"]},
            marks=pytest.mark.polarion("CNV-3637"),
        ),
    ],
    indirect=True,
)
def test_successful_vm_from_imported_dv_windows(
    skip_upstream,
    unprivileged_client,
    namespace,
    data_volume_multi_storage_scope_function,
    vm_instance_from_template_multi_storage_scope_function,
    started_windows_vm,
):
    validate_vmi_ga_info_vs_windows_os_info(
        vm=vm_instance_from_template_multi_storage_scope_function,
    )


@pytest.mark.polarion("CNV-4032")
def test_disk_image_after_import(
    skip_block_volumemode_scope_module,
    images_internal_http_server,
    namespace,
    storage_class_matrix__module__,
    unprivileged_client,
):
    with utilities.storage.create_dv(
        source="http",
        dv_name="cnv-4032",
        namespace=namespace.name,
        url=f"{utilities.storage.get_images_external_http_server()}{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
        size="2Gi",
        client=unprivileged_client,
        **utils.storage_params(storage_class_matrix=storage_class_matrix__module__),
    ) as dv:
        utils.create_vm_and_verify_image_permission(dv=dv)


@pytest.mark.polarion("CNV-4724")
def test_dv_api_version_after_import(
    images_internal_http_server,
    namespace,
    storage_class_matrix__module__,
    unprivileged_client,
):
    with utilities.storage.create_dv(
        dv_name="cnv-4724",
        namespace=namespace.name,
        url=f"{utilities.storage.get_images_external_http_server()}{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
        size=Images.Cirros.DEFAULT_DV_SIZE,
        client=unprivileged_client,
        **utils.storage_params(storage_class_matrix=storage_class_matrix__module__),
    ) as dv:
        assert dv.api_version == f"{dv.api_group}/{dv.ApiVersion.V1BETA1}"


@pytest.mark.polarion("CNV-5509")
def test_importer_pod_annotation(dv_with_annotation, linux_nad):
    # verify "k8s.v1.cni.cncf.io/networks" can pass to the importer pod
    assert (
        dv_with_annotation.get(f"{Resource.ApiGroup.K8S_V1_CNI_CNCF_IO}/networks")
        == linux_nad.name
    )
    assert '"interface": "net1"' in dv_with_annotation.get(
        f"{Resource.ApiGroup.K8S_V1_CNI_CNCF_IO}/network-status"
    )
