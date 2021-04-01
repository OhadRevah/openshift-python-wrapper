# -*- coding: utf-8 -*-

"""
Upload tests
"""

import logging
import multiprocessing
import time
from time import sleep

import pytest
import sh
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume import PersistentVolume
from ocp_resources.route import Route
from ocp_resources.upload_token_request import UploadTokenRequest
from ocp_resources.utils import TimeoutSampler
from pytest_testconfig import config as py_config
from string_utils import shuffle

import tests.storage.utils as storage_utils
import utilities.storage
from utilities.infra import Images
from utilities.storage import downloaded_image


LOGGER = logging.getLogger(__name__)
HTTP_UNAUTHORIZED = 401
HTTP_OK = 200


def wait_for_upload_response_code(token, data, response_code, asynchronous=False):
    kwargs = {
        "wait_timeout": 60,
        "sleep": 5,
        "func": storage_utils.upload_image,
        "token": token,
        "data": data,
    }
    if asynchronous:
        kwargs["asynchronous"] = asynchronous
    sampler = TimeoutSampler(**kwargs)
    for sample in sampler:
        if sample == response_code:
            return True


@pytest.mark.polarion("CNV-2318")
def test_cdi_uploadproxy_route_owner_references(skip_not_openshift):
    route = Route(name="cdi-uploadproxy", namespace=py_config["hco_namespace"])
    assert route.instance
    assert route.instance["metadata"]["ownerReferences"][0]["name"] == "cdi-deployment"
    assert route.instance["metadata"]["ownerReferences"][0]["kind"] == "Deployment"


@pytest.mark.parametrize(
    ("dv_name", "remote_name", "local_name"),
    [
        pytest.param(
            "cnv-875",
            f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
            Images.Cirros.QCOW2_IMG,
            marks=(pytest.mark.polarion("CNV-875")),
            id=f"cnv-875-{Images.Cirros.QCOW2_IMG}",
        ),
        pytest.param(
            "cnv-2007",
            f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG_GZ}",
            Images.Cirros.QCOW2_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2007"), pytest.mark.post_upgrade()),
            id=f"cnv-2007-{Images.Cirros.QCOW2_IMG_GZ}",
        ),
        pytest.param(
            "cnv-2007",
            f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG_XZ}",
            Images.Cirros.QCOW2_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-2007")),
            id=f"cnv-2007-{Images.Cirros.QCOW2_IMG_XZ}",
        ),
        pytest.param(
            "cnv-2007",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG}",
            Images.Cirros.RAW_IMG,
            marks=(pytest.mark.polarion("CNV-2007")),
            id=f"cnv-2007-{Images.Cirros.RAW_IMG}",
        ),
        pytest.param(
            "cnv-2007",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG_GZ}",
            Images.Cirros.RAW_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2007")),
            id=f"cnv-2007-{Images.Cirros.RAW_IMG_GZ}",
        ),
        pytest.param(
            "cnv-2007",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG_XZ}",
            Images.Cirros.RAW_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-2007")),
            id=f"cnv-2007-{Images.Cirros.RAW_IMG_XZ}",
        ),
        pytest.param(
            "cnv-2008",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG}",
            Images.Cirros.QCOW2_IMG,
            marks=(pytest.mark.polarion("CNV-2008")),
            id=f"cnv-2008-{Images.Cirros.RAW_IMG}-saved-as-{Images.Cirros.QCOW2_IMG}",
        ),
        pytest.param(
            "cnv-2008",
            f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
            Images.Cirros.QCOW2_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-2008")),
            id=f"cnv-2008-{Images.Cirros.QCOW2_IMG}-saved-as-{Images.Cirros.QCOW2_IMG_XZ}",
        ),
        pytest.param(
            "cnv-2008",
            f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
            Images.Cirros.QCOW2_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2008")),
            id=f"cnv-2008-{Images.Cirros.QCOW2_IMG}-saved-as-{Images.Cirros.QCOW2_IMG_GZ}",
        ),
        pytest.param(
            "cnv-2008",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG}",
            Images.Cirros.RAW_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-2008")),
            id=f"cnv-2008-{Images.Cirros.RAW_IMG}-saved-as-{Images.Cirros.RAW_IMG_XZ}",
        ),
        pytest.param(
            "cnv-2008",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG}",
            Images.Cirros.RAW_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2008")),
            id=f"cnv-2008-{Images.Cirros.RAW_IMG}-saved-as-{Images.Cirros.RAW_IMG_GZ}",
        ),
        pytest.param(
            "cnv-2008",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG_GZ}",
            Images.Cirros.RAW_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-2008")),
            id=f"cnv-2008-{Images.Cirros.RAW_IMG_GZ}-saved-as-{Images.Cirros.RAW_IMG_XZ}",
        ),
        pytest.param(
            "cnv-2008",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG_XZ}",
            Images.Cirros.RAW_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2008")),
            id=f"cnv-2008-{Images.Cirros.RAW_IMG_XZ}-saved-as-{Images.Cirros.RAW_IMG_GZ}",
        ),
    ],
)
def test_successful_upload_with_supported_formats(
    skip_upstream,
    namespace,
    tmpdir,
    storage_class_matrix__module__,
    dv_name,
    remote_name,
    local_name,
    unprivileged_client,
):
    storage_class = [*storage_class_matrix__module__][0]
    local_name = f"{tmpdir}/{local_name}"
    downloaded_image(remote_name=remote_name, local_name=local_name)
    with storage_utils.upload_image_to_dv(
        dv_name=dv_name,
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
        storage_ns_name=namespace.name,
        client=unprivileged_client,
    ) as dv:
        storage_utils.upload_token_request(
            storage_ns_name=namespace.name, pvc_name=dv.pvc.name, data=local_name
        )
        dv.wait()
        with storage_utils.create_vm_from_dv(dv=dv) as vm_dv:
            storage_utils.check_disk_count_in_vm(vm=vm_dv)


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cnv-2018",
                "source": "upload",
                "dv_size": "3Gi",
                "wait": False,
            },
            marks=(pytest.mark.polarion("CNV-2018")),
        ),
    ],
    indirect=True,
)
@pytest.mark.polarion("CNV-2018")
def test_successful_upload_token_validity(
    skip_upstream,
    namespace,
    data_volume_multi_storage_scope_function,
    upload_file_path,
):
    dv = data_volume_multi_storage_scope_function
    dv.wait_for_condition(
        condition=DataVolume.Condition.Type.BOUND,
        status=DataVolume.Condition.Status.TRUE,
        timeout=300,
    )
    dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=180)
    with UploadTokenRequest(
        name=dv.name,
        namespace=namespace.name,
        pvc_name=dv.pvc.name,
    ) as utr:
        token = utr.create().status.token
        wait_for_upload_response_code(
            token=shuffle(token), data="test", response_code=HTTP_UNAUTHORIZED
        )
    with UploadTokenRequest(
        name=dv.name,
        namespace=namespace.name,
        pvc_name=dv.pvc.name,
    ) as utr:
        token = utr.create().status.token
        wait_for_upload_response_code(
            token=token, data=upload_file_path, response_code=HTTP_OK
        )
        dv.wait_for_condition(
            condition=DataVolume.Condition.Type.RUNNING,
            status=DataVolume.Condition.Status.TRUE,
            timeout=300,
        )
        dv.wait_for_condition(
            condition=DataVolume.Condition.Type.READY,
            status=DataVolume.Condition.Status.TRUE,
            timeout=300,
        )


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cnv-2011",
                "source": "upload",
                "dv_size": "3Gi",
                "wait": False,
            },
            marks=(pytest.mark.polarion("CNV-2011")),
        ),
    ],
    indirect=True,
)
@pytest.mark.polarion("CNV-2011")
def test_successful_upload_token_expiry(
    skip_upstream, namespace, data_volume_multi_storage_scope_function
):
    dv = data_volume_multi_storage_scope_function
    dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=180)
    with UploadTokenRequest(
        name=dv.name,
        namespace=namespace.name,
        pvc_name=dv.pvc.name,
    ) as utr:
        token = utr.create().status.token
        LOGGER.info("Wait until token expires ...")
        time.sleep(310)
        wait_for_upload_response_code(
            token=token, data="test", response_code=HTTP_UNAUTHORIZED
        )


def _upload_image(
    dv_name, namespace, storage_class, volume_mode, local_name, size=None
):
    """
    Upload image function for the use of other tests
    """
    size = size or "3Gi"
    with utilities.storage.create_dv(
        source="upload",
        dv_name=dv_name,
        namespace=namespace.name,
        size=size,
        storage_class=storage_class,
        volume_mode=volume_mode,
    ) as dv:
        LOGGER.info("Wait for DV to be UploadReady")
        dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=300)
        with UploadTokenRequest(
            name=dv_name,
            namespace=namespace.name,
            pvc_name=dv.pvc.name,
        ) as utr:
            token = utr.create().status.token
            sleep(5)
            LOGGER.info("Ensure upload was successful")
            wait_for_upload_response_code(
                token=token, data=local_name, response_code=HTTP_OK
            )


@pytest.mark.polarion("CNV-2015")
def test_successful_concurrent_uploads(
    skip_upstream,
    upload_file_path,
    namespace,
    storage_class_matrix__module__,
):
    dvs_processes = []
    storage_class = [*storage_class_matrix__module__][0]
    volume_mode = storage_class_matrix__module__[storage_class]["volume_mode"]
    available_pv = PersistentVolume(name=namespace).max_available_pvs
    for dv in range(available_pv):
        dv_process = multiprocessing.Process(
            target=_upload_image,
            args=(f"dv-{dv}", namespace, storage_class, volume_mode, upload_file_path),
        )
        dv_process.start()
        dvs_processes.append(dv_process)

    for dvs in dvs_processes:
        dvs.join()
        if dvs.exitcode != 0:
            raise pytest.fail("Creating DV exited with non-zero return code")


@pytest.mark.parametrize(
    "upload_file_path",
    [
        pytest.param(
            {
                "remote_image_dir": Images.Rhel.DIR,
                "remote_image_name": Images.Rhel.RHEL8_0_IMG,
            },
            marks=(pytest.mark.polarion("CNV-2017")),
        ),
    ],
    indirect=True,
)
def test_successful_upload_missing_file_in_transit(
    skip_upstream, namespace, storage_class_matrix__class__, upload_file_path
):
    dv_name = "cnv-2017"
    storage_class = [*storage_class_matrix__class__][0]
    volume_mode = storage_class_matrix__class__[storage_class]["volume_mode"]
    downloaded_image(
        remote_name=f"{Images.Rhel.DIR}/{Images.Rhel.RHEL8_0_IMG}",
        local_name=upload_file_path,
    )
    upload_process = multiprocessing.Process(
        target=_upload_image,
        args=(dv_name, namespace, storage_class, volume_mode, upload_file_path, "10Gi"),
    )

    # Run process in parallel
    upload_process.start()

    # Ideally the file should be removed while the status of upload is 'UploadInProgress'.
    # However, 'UploadInProgress' status phase is never set.
    # Sleep for 15 seconds until https://bugzilla.redhat.com/show_bug.cgi?id=1725934 is fixed.
    # Once the bug is fixed, the below line needs to be uncommented and sleep should be removed.
    # DataVolume(dv_name, namespace).wait_for_status(status="UploadInProgress", timeout=300)
    time.sleep(15)
    sh.rm("-f", upload_file_path)

    # Exit the completed processes
    upload_process.join()


@pytest.mark.parametrize(
    "download_specified_image, data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "image_path": py_config["latest_rhel_os_dict"]["image_path"],
                "image_file": py_config["latest_rhel_os_dict"]["image_name"],
            },
            {
                "dv_name": "cnv-4511",
                "source": "upload",
                "dv_size": "3Gi",
                "wait": True,
            },
            marks=(pytest.mark.polarion("CNV-4511")),
        ),
    ],
    indirect=True,
)
def test_print_response_body_on_error_upload(
    namespace,
    download_specified_image,
    data_volume_multi_storage_scope_function,
):
    """
    Check that CDI now reports validation failures as part of the body response
    in case for instance the disk image virtual size > PVC size > disk size
    """
    dv = data_volume_multi_storage_scope_function
    with UploadTokenRequest(
        name=dv.name,
        namespace=dv.namespace,
        pvc_name=dv.pvc.name,
    ) as utr:
        token = utr.create().status.token
        LOGGER.debug("Start upload an image asynchronously ...")

        # Upload should fail with an error
        wait_for_upload_response_code(
            token=token,
            data=download_specified_image,
            response_code=400,
            asynchronous=True,
        )
