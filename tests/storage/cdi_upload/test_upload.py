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
import tests.storage.utils as storage_utils
import utilities.storage
from pytest_testconfig import config as py_config
from resources.datavolume import DataVolume
from resources.persistent_volume import PersistentVolume
from resources.route import Route
from resources.upload_token_request import UploadTokenRequest
from resources.utils import TimeoutSampler
from string_utils import shuffle
from utilities.infra import Images


LOGGER = logging.getLogger(__name__)


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
        ),
        pytest.param(
            "cnv-2007",
            f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG_GZ}",
            Images.Cirros.QCOW2_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2007")),
        ),
        pytest.param(
            "cnv-2007",
            f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG_XZ}",
            Images.Cirros.QCOW2_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-2007")),
        ),
        pytest.param(
            "cnv-2007",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG}",
            Images.Cirros.RAW_IMG,
            marks=(pytest.mark.polarion("CNV-2007")),
        ),
        pytest.param(
            "cnv-2007",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG_GZ}",
            Images.Cirros.RAW_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2007")),
        ),
        pytest.param(
            "cnv-2007",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG_XZ}",
            Images.Cirros.RAW_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-2007")),
        ),
        pytest.param(
            "cnv-2008",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG}",
            Images.Cirros.QCOW2_IMG,
            marks=(pytest.mark.polarion("CNV-2008")),
        ),
        pytest.param(
            "cnv-2008",
            f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
            Images.Cirros.QCOW2_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-2008")),
        ),
        pytest.param(
            "cnv-2008",
            f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
            Images.Cirros.QCOW2_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2008")),
        ),
        pytest.param(
            "cnv-2008",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG}",
            Images.Cirros.RAW_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-2008")),
        ),
        pytest.param(
            "cnv-2008",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG}",
            Images.Cirros.RAW_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2008")),
        ),
        pytest.param(
            "cnv-2008",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG_GZ}",
            Images.Cirros.RAW_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-2008")),
        ),
        pytest.param(
            "cnv-2008",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG_XZ}",
            Images.Cirros.RAW_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2008")),
        ),
    ],
)
def test_successful_upload_with_supported_formats(
    skip_upstream,
    namespace,
    tmpdir,
    dv_name,
    remote_name,
    local_name,
    storage_class_matrix__module__,
):
    storage_class = [*storage_class_matrix__module__][0]
    local_name = f"{tmpdir}/{local_name}"
    storage_utils.downloaded_image(remote_name=remote_name, local_name=local_name)
    with storage_utils.upload_image_to_dv(
        dv_name=dv_name,
        storage_class=storage_class,
        volume_mode=storage_class_matrix__module__[storage_class]["volume_mode"],
        storage_ns_name=namespace.name,
    ) as dv:
        storage_utils.upload_token_request(
            storage_ns_name=namespace.name, pvc_name=dv.pvc.name, data=local_name
        )
        dv.wait()
        with storage_utils.create_vm_from_dv(dv=dv) as vm_dv:
            storage_utils.check_disk_count_in_vm(vm=vm_dv)


@pytest.mark.polarion("CNV-2018")
def test_successful_upload_token_validity(
    skip_upstream, namespace, tmpdir, default_client
):
    dv_name = "cnv-2018"
    local_name = f"{tmpdir}/{Images.Cirros.QCOW2_IMG}"
    storage_utils.downloaded_image(
        remote_name=f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
        local_name=local_name,
    )
    with utilities.storage.create_dv(
        source="upload",
        dv_name=dv_name,
        namespace=namespace.name,
        size="3Gi",
        storage_class=py_config["default_storage_class"],
        volume_mode=py_config["default_volume_mode"],
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=180)
        with UploadTokenRequest(
            name=dv_name, namespace=namespace.name, pvc_name=dv.pvc.name,
        ) as utr:
            token = utr.create().status.token
            sampler = TimeoutSampler(
                timeout=60,
                sleep=5,
                func=storage_utils.upload_image,
                token=shuffle(token),
                data=local_name,
            )
            for sample in sampler:
                if sample == 401:
                    return True
        with UploadTokenRequest(
            name=dv_name, namespace=namespace.name, pvc_name=dv.pvc.name,
        ) as utr:
            token = utr.create().status.token
            sampler = TimeoutSampler(
                timeout=60,
                sleep=5,
                func=storage_utils.upload_image,
                token=token,
                data=local_name,
            )
            for sample in sampler:
                if sample == 200:
                    return True


@pytest.mark.polarion("CNV-2011")
def test_successful_upload_token_expiry(
    skip_upstream, namespace, tmpdir, default_client
):
    dv_name = "cnv-2011"
    local_name = f"{tmpdir}/{Images.Cirros.QCOW2_IMG}"
    storage_utils.downloaded_image(
        remote_name=f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
        local_name=local_name,
    )
    with utilities.storage.create_dv(
        source="upload",
        dv_name=dv_name,
        namespace=namespace.name,
        size="3Gi",
        storage_class=py_config["default_storage_class"],
        volume_mode=py_config["default_volume_mode"],
    ) as dv:
        LOGGER.info("Wait for DV to be UploadReady")
        dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=120)
        with UploadTokenRequest(
            name=dv_name, namespace=namespace.name, pvc_name=dv.pvc.name,
        ) as utr:
            token = utr.create().status.token
            LOGGER.info("Wait until token expires ...")
            time.sleep(310)
            sampler = TimeoutSampler(
                timeout=60,
                sleep=5,
                func=storage_utils.upload_image,
                token=token,
                data=local_name,
            )
            for sample in sampler:
                if sample == 401:
                    return True


def _upload_image(dv_name, namespace, local_name, size=None):
    """
    Upload test that is executed in parallel in with other tasks.
    """
    size = size or "3Gi"
    with utilities.storage.create_dv(
        source="upload",
        dv_name=dv_name,
        namespace=namespace.name,
        size=size,
        storage_class=py_config["default_storage_class"],
        volume_mode=py_config["default_volume_mode"],
    ) as dv:
        LOGGER.info("Wait for DV to be UploadReady")
        dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=300)
        with UploadTokenRequest(
            name=dv_name, namespace=namespace.name, pvc_name=dv.pvc.name,
        ) as utr:
            token = utr.create().status.token
            sleep(5)
            LOGGER.info("Ensure upload was successful")
            sampler = TimeoutSampler(
                timeout=60,
                sleep=5,
                func=storage_utils.upload_image,
                token=token,
                data=local_name,
            )
            for sample in sampler:
                if sample == 200:
                    return True


@pytest.mark.polarion("CNV-2015")
def test_successful_concurrent_uploads(
    skip_upstream, namespace, tmpdir, default_client
):
    dvs_processes = []
    local_name = f"{tmpdir}/{Images.Cirros.QCOW2_IMG}"
    storage_utils.downloaded_image(
        remote_name=f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
        local_name=local_name,
    )
    available_pv = PersistentVolume(namespace).max_available_pvs
    for dv in range(available_pv):
        dv_process = multiprocessing.Process(
            target=_upload_image, args=(f"dv-{dv}", namespace, local_name),
        )
        dv_process.start()
        dvs_processes.append(dv_process)

    for dvs in dvs_processes:
        dvs.join()
        if dvs.exitcode != 0:
            raise pytest.fail("Creating DV exited with non-zero return code")


@pytest.mark.polarion("CNV-2017")
def test_successful_upload_missing_file_in_transit(
    skip_upstream, tmpdir, namespace, default_client
):
    dv_name = "cnv-2017"
    local_name = f"{tmpdir}/{Images.Rhel.RHEL8_0_IMG}"
    storage_utils.downloaded_image(
        remote_name=f"{Images.Rhel.DIR}/{Images.Rhel.RHEL8_0_IMG}",
        local_name=local_name,
    )
    upload_process = multiprocessing.Process(
        target=_upload_image, args=(dv_name, namespace, local_name, "10Gi"),
    )

    # Run process in parallel
    upload_process.start()

    # Ideally the file should be removed while the status of upload is 'UploadInProgress'.
    # However, 'UploadInProgress' status phase is never set.
    # Sleep for 15 seconds until https://bugzilla.redhat.com/show_bug.cgi?id=1725934 is fixed.
    # Once the bug is fixed, the below line needs to be uncommented and sleep should be removed.
    # DataVolume(dv_name, namespace).wait_for_status(status="UploadInProgress", timeout=300)
    time.sleep(15)
    sh.rm("-f", local_name)

    # Exit the completed processes
    upload_process.join()
