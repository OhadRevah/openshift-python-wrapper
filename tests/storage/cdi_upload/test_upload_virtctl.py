# -*- coding: utf-8 -*-

"""
Upload using virtctl
"""

import logging

import pytest
import tests.storage.utils as storage_utils
from openshift.dynamic.exceptions import NotFoundError
from pytest_testconfig import config as py_config
from resources.datavolume import DataVolume
from resources.persistent_volume_claim import PersistentVolumeClaim
from resources.route import Route
from utilities import console
from utilities.infra import ErrorMsg, Images
from utilities.storage import create_dv
from utilities.virt import VirtualMachineForTests, wait_for_console


LOGGER = logging.getLogger(__name__)
LOCAL_PATH = f"/tmp/{Images.Cdi.QCOW2_IMG}"


@pytest.fixture(scope="function")
def skip_no_reencrypt_route(upload_proxy_route):
    LOGGER.debug("Use 'skip_no_reencrypt_route' fixture...")
    if not upload_proxy_route.termination == "reencrypt":
        pytest.skip(msg="Skip testing. The upload proxy route is not re-encrypt.")


@pytest.mark.polarion("CNV-2192")
def test_successful_virtctl_upload_no_url(namespace, tmpdir):
    local_name = f"{tmpdir}/{Images.Cdi.QCOW2_IMG}"
    storage_utils.downloaded_image(
        remote_name=f"{Images.Cdi.DIR}/{Images.Cdi.QCOW2_IMG}", local_name=local_name
    )
    pvc_name = "cnv-2192"
    with storage_utils.virtctl_upload_dv(
        namespace=namespace.name,
        name=pvc_name,
        size="1Gi",
        storage_class=py_config["default_storage_class"],
        image_path=local_name,
        insecure=True,
    ) as virtctl_upload:
        assert virtctl_upload
        LOGGER.info(f"{virtctl_upload}")
        assert PersistentVolumeClaim(name=pvc_name, namespace=namespace.name).bound()


@pytest.mark.destructive
@pytest.mark.polarion("CNV-2191")
def test_successful_virtctl_upload_no_route(
    skip_not_openshift,
    namespace,
    tmpdir,
    uploadproxy_route_deleted,
):
    route = Route(name="cdi-uploadproxy", namespace=py_config["hco_namespace"])
    with pytest.raises(NotFoundError):
        route.instance

    local_name = f"{tmpdir}/{Images.Cdi.QCOW2_IMG}"
    storage_utils.downloaded_image(
        remote_name=f"{Images.Cdi.DIR}/{Images.Cdi.QCOW2_IMG}", local_name=local_name
    )
    pvc_name = "cnv-2191"
    with storage_utils.virtctl_upload_dv(
        namespace=namespace.name,
        name=pvc_name,
        size="1Gi",
        storage_class=py_config["default_storage_class"],
        image_path=local_name,
        insecure=True,
    ) as res:
        virtctl_upload, virtctl_upload_out = res
        LOGGER.info(f"{virtctl_upload_out}")
        assert (
            virtctl_upload is False
        ), "virtctl image-upload command successful, must fail with a non-zero rc"


@pytest.mark.polarion("CNV-2217")
def test_image_upload_with_overridden_url(
    skip_not_openshift,
    namespace,
    tmpdir,
    new_route_created,
    cdi_config_upload_proxy_overridden,
):
    pvc_name = "cnv-2217"
    local_name = f"{tmpdir}/{Images.Cdi.QCOW2_IMG}"
    storage_utils.downloaded_image(
        remote_name=f"{Images.Cdi.DIR}/{Images.Cdi.QCOW2_IMG}", local_name=local_name
    )
    with storage_utils.virtctl_upload_dv(
        namespace=namespace.name,
        name=pvc_name,
        size="1Gi",
        storage_class=py_config["default_storage_class"],
        image_path=local_name,
        insecure=True,
    ) as virtctl_upload:
        assert virtctl_upload
        LOGGER.info(f"{virtctl_upload}")
        assert PersistentVolumeClaim(name=pvc_name, namespace=namespace.name).bound()


@pytest.mark.polarion("CNV-3031")
def test_virtctl_image_upload_with_ca(
    skip_no_reencrypt_route,
    skip_router_wildcard_cert_not_trusted,
    skip_not_openshift,
    tmpdir,
    namespace,
):
    local_path = f"{tmpdir}/{Images.Cdi.QCOW2_IMG}"
    storage_utils.downloaded_image(
        remote_name=f"{Images.Cdi.DIR}/{Images.Cdi.QCOW2_IMG}", local_name=local_path
    )
    pvc_name = "cnv-3031"
    with storage_utils.virtctl_upload_dv(
        namespace=namespace.name,
        name=pvc_name,
        size="1Gi",
        storage_class=py_config["default_storage_class"],
        image_path=local_path,
    ) as res:
        status, out = res
        LOGGER.info(out)
        assert status
        pvc = PersistentVolumeClaim(namespace=namespace.name, name=pvc_name)
        assert pvc.bound()


@pytest.mark.polarion("CNV-3724")
def test_virtctl_image_upload_dv(
    download_image, namespace, storage_class_matrix__module__
):
    """
    Check that upload a local disk image to a newly created DataVolume
    """
    storage_class = [*storage_class_matrix__module__][0]
    dv_name = f"cnv-3724-{storage_class}"
    with storage_utils.virtctl_upload_dv(
        namespace=namespace.name,
        name=dv_name,
        size="1Gi",
        image_path=LOCAL_PATH,
        storage_class=storage_class,
        insecure=True,
    ) as res:
        status, out = res
        LOGGER.info(out)
        assert status
        assert "Processing completed successfully" in out
        dv = DataVolume(namespace=namespace.name, name=dv_name)
        dv.wait(timeout=60)
        with storage_utils.create_vm_from_dv(dv=dv, start=True) as vm:
            wait_for_console(vm=vm, console_impl=console.Cirros)


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cnv-3726",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
            },
            marks=(pytest.mark.polarion("CNV-3726")),
        ),
    ],
    indirect=True,
)
def test_virtctl_image_upload_with_exist_dv_image(
    data_volume_multi_storage_scope_function,
    download_image,
    namespace,
):
    """
    Check that virtctl fails gracefully when attempting to upload an image to a data volume that already has disk.img
    """
    with storage_utils.virtctl_upload_dv(
        namespace=namespace.name,
        name=data_volume_multi_storage_scope_function.name,
        size="1Gi",
        image_path=LOCAL_PATH,
        storage_class=data_volume_multi_storage_scope_function.storage_class,
        insecure=True,
        no_create=True,
    ) as res:
        status, out = res
        LOGGER.info(out)
        assert not status
        assert (
            f"PVC {data_volume_multi_storage_scope_function.name} already successfully imported/cloned/updated"
            in out
        )


@pytest.mark.polarion("CNV-3728")
def test_virtctl_image_upload_pvc(
    download_image, namespace, storage_class_matrix__module__
):
    """
    Check that virtctl can create a new PVC and upload an image to it
    """
    pvc_name = "cnv-3728"
    with storage_utils.virtctl_upload_dv(
        namespace=namespace.name,
        pvc=True,
        name=pvc_name,
        size="1Gi",
        image_path=LOCAL_PATH,
        storage_class=[*storage_class_matrix__module__][0],
        insecure=True,
    ) as res:
        status, out = res
        LOGGER.info(out)
        assert status
        pvc = PersistentVolumeClaim(namespace=namespace.name, name=pvc_name)
        assert pvc.bound()


@pytest.mark.polarion("CNV-3725")
def test_virtctl_image_upload_with_exist_dv(
    download_image, namespace, storage_class_matrix__module__
):
    """
    Check that virtctl is able to upload a local disk image to an existing DataVolume
    """
    storage_class = [*storage_class_matrix__module__][0]
    dv_name = "cnv-3725"
    with create_dv(
        source="upload",
        dv_name=dv_name,
        namespace=namespace.name,
        size="1Gi",
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=120)
        with storage_utils.virtctl_upload_dv(
            namespace=namespace.name,
            name=dv.name,
            size="1Gi",
            image_path=LOCAL_PATH,
            insecure=True,
            storage_class=storage_class,
            no_create=True,
        ) as res:
            status, out = res
            LOGGER.info(out)
            assert "Processing completed successfully" in out
            with storage_utils.create_vm_from_dv(dv=dv, start=True) as vm:
                wait_for_console(vm=vm, console_impl=console.Cirros)


@pytest.fixture()
def empty_pvc(namespace, storage_class_matrix__module__, worker_node1):
    LOGGER.debug("Use 'empty_pvc' fixture...")
    storage_class = [*storage_class_matrix__module__][0]
    with PersistentVolumeClaim(
        name="empty-pvc",
        namespace=namespace.name,
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
        accessmodes=storage_class_matrix__module__[storage_class]["access_mode"],
        size="1Gi",
        hostpath_node=worker_node1.name,
    ) as pvc:
        pvc.wait_for_status(status=PersistentVolumeClaim.Status.BOUND, timeout=60)
        yield pvc


@pytest.mark.polarion("CNV-3727")
def test_virtctl_image_upload_with_exist_pvc(
    empty_pvc,
    download_image,
    namespace,
    storage_class_matrix__module__,
    schedulable_nodes,
):
    """
    Check that virtctl can upload an local disk image to an existing empty PVC
    """
    storage_class = [*storage_class_matrix__module__][0]
    with storage_utils.virtctl_upload_dv(
        namespace=namespace.name,
        name=empty_pvc.name,
        size="1Gi",
        image_path=LOCAL_PATH,
        storage_class=storage_class,
        insecure=True,
        no_create=True,
    ) as res:
        status, out = res
        LOGGER.info(out)
        assert "Processing completed successfully" in out
        with VirtualMachineForTests(
            name="cnv-3727-vm",
            namespace=empty_pvc.namespace,
            pvc=empty_pvc,
        ) as vm:
            vm.start(wait=True)
            vm.vmi.wait_until_running(timeout=300)
            wait_for_console(vm=vm, console_impl=console.Cirros)


@pytest.mark.polarion("CNV-3729")
def test_virtctl_image_upload_with_exist_pvc_image(
    download_image, namespace, storage_class_matrix__module__
):
    """
    Check that virtctl fails gracefully when attempting to upload an image to a PVC that already has disk.img
    """
    storage_class = [*storage_class_matrix__module__][0]
    pvc_name = f"cnv-3729-{storage_class}"
    with storage_utils.virtctl_upload_dv(
        namespace=namespace.name,
        name=pvc_name,
        size="1Gi",
        image_path=LOCAL_PATH,
        storage_class=storage_class,
        insecure=True,
    ) as res:
        status, out = res
        LOGGER.info(out)
        assert "Processing completed successfully" in out
        with storage_utils.virtctl_upload_dv(
            namespace=namespace.name,
            name=pvc_name,
            size="1Gi",
            image_path=LOCAL_PATH,
            storage_class=storage_class,
            insecure=True,
            no_create=True,
        ) as res_new:
            status_new, out_new = res_new
            LOGGER.info(out_new)
            assert not status_new
            assert (
                f"PVC {pvc_name} already successfully imported/cloned/updated"
                in out_new
            )


@pytest.mark.polarion("CNV-3730")
def test_virtctl_image_upload_dv_with_exist_pvc(
    empty_pvc,
    download_image,
    namespace,
    storage_class_matrix__module__,
    schedulable_nodes,
):
    """
    Check that virtctl fails gracefully when attempting to upload an image to a new data volume
    - PVC with the same name already exists.
    """
    storage_class = [*storage_class_matrix__module__][0]
    with storage_utils.virtctl_upload_dv(
        namespace=namespace.name,
        name=empty_pvc.name,
        size="1Gi",
        image_path=LOCAL_PATH,
        storage_class=storage_class,
        insecure=True,
    ) as res:
        status, out = res
        LOGGER.info(out)
        assert not status
        assert f"PVC {empty_pvc.name} not available for upload" in out


@pytest.mark.tier3
@pytest.mark.parametrize(
    ("uploaded_dv", "vm_params"),
    [
        pytest.param(
            {
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
                "remote_name": py_config["latest_windows_version"]["image_path"],
                "image_file": py_config["latest_windows_version"]["image_name"],
            },
            {
                "vm_name": f"vm-win-{py_config['latest_windows_version']['os_version']}",
                "template_labels": py_config["latest_windows_version"][
                    "template_labels"
                ],
                "cpu_threads": 2,
                "os_version": py_config["latest_windows_version"]["os_version"],
            },
            marks=(pytest.mark.polarion("CNV-3410")),
        ),
    ],
    indirect=["uploaded_dv"],
)
def test_successful_vm_from_uploaded_dv_windows(
    skip_upstream,
    uploaded_dv,
    unprivileged_client,
    network_configuration,
    cloud_init_data,
    vm_params,
    namespace,
    winrmcli_pod_scope_function,
    bridge_attached_helper_vm,
):
    storage_utils.create_windows_vm_validate_guest_agent_info(
        cloud_init_data=cloud_init_data,
        bridge_attached_helper_vm=bridge_attached_helper_vm,
        dv=uploaded_dv,
        namespace=namespace,
        network_configuration=network_configuration,
        unprivileged_client=unprivileged_client,
        vm_params=vm_params,
        winrmcli_pod_scope_function=winrmcli_pod_scope_function,
    )


@pytest.mark.polarion("CNV-4033")
def test_disk_image_after_upload_virtctl(
    skip_block_volumemode_scope_module,
    download_image,
    namespace,
    storage_class_matrix__module__,
    unprivileged_client,
):
    storage_class = [*storage_class_matrix__module__][0]
    dv_name = f"cnv-4033-{storage_class}"
    with storage_utils.virtctl_upload_dv(
        namespace=namespace.name,
        name=dv_name,
        size="1Gi",
        image_path=LOCAL_PATH,
        storage_class=storage_class,
        insecure=True,
    ) as res:
        status, out = res
        LOGGER.info(out)
        assert status
        dv = DataVolume(namespace=namespace.name, name=dv_name)
        storage_utils.create_vm_and_verify_image_permission(dv=dv)


@pytest.mark.parametrize(
    "download_specified_image",
    [
        pytest.param(
            {
                "image_path": py_config["latest_rhel_version"]["image_path"],
                "image_file": py_config["latest_rhel_version"]["image_name"],
            },
            marks=(pytest.mark.polarion("CNV-4512")),
        ),
    ],
    indirect=True,
)
def test_print_response_body_on_error_upload_virtctl(
    namespace, download_specified_image, storage_class_matrix__module__
):
    """
    Check that CDI now reports validation failures as part of the body response
    in case for instance the disk image virtual size > PVC size > disk size
    """
    storage_class = [*storage_class_matrix__module__][0]
    dv_name = f"cnv-4512-{storage_class}"
    with storage_utils.virtctl_upload_dv(
        namespace=namespace.name,
        name=dv_name,
        size="3G",
        image_path=download_specified_image,
        storage_class=storage_class,
        insecure=True,
    ) as res:
        status, out = res
        LOGGER.info(out)
        assert not status
        assert ErrorMsg.LARGER_PVC_REQUIRED in out
