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
from pytest_testconfig import config as py_config
from resources.datavolume import UploadDataVolume
from resources.persistent_volume import PersistentVolume
from resources.upload_token_request import UploadTokenRequest
from resources.utils import TimeoutSampler
from string_utils import shuffle
from utilities.infra import Images


LOGGER = logging.getLogger(__name__)
CDI_IMAGES_DIR = "cdi-test-images"
RHEL8_IMAGES = "rhel-images/rhel-8"
QCOW2_IMG = "cirros-qcow2.img"
RAW_IMG = "cirros.raw"
RHEL8_QCOW2 = "rhel-8.qcow2"


@pytest.mark.parametrize(
    ("dv_name", "remote_name", "local_name"),
    [
        pytest.param(
            "cnv-875",
            f"{CDI_IMAGES_DIR}/{QCOW2_IMG}",
            QCOW2_IMG,
            marks=(pytest.mark.polarion("CNV-875")),
        ),
        pytest.param(
            "cnv-2007",
            f"{CDI_IMAGES_DIR}/cirros_images/{Images.Cirros.QCOW2_IMG_GZ}",
            Images.Cirros.QCOW2_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2007")),
        ),
        pytest.param(
            "cnv-2007",
            f"{CDI_IMAGES_DIR}/cirros_images/{Images.Cirros.QCOW2_IMG_XZ}",
            Images.Cirros.QCOW2_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-2007")),
        ),
        pytest.param(
            "cnv-2007",
            f"{CDI_IMAGES_DIR}/{RAW_IMG}",
            RAW_IMG,
            marks=(pytest.mark.polarion("CNV-2007")),
        ),
        pytest.param(
            "cnv-2007",
            f"{CDI_IMAGES_DIR}/cirros_images/{Images.Cirros.RAW_IMG_GZ}",
            Images.Cirros.RAW_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2007")),
        ),
        pytest.param(
            "cnv-2007",
            f"{CDI_IMAGES_DIR}/cirros_images/{Images.Cirros.RAW_IMG_XZ}",
            Images.Cirros.RAW_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2007")),
        ),
        pytest.param(
            "cnv-2008",
            f"{CDI_IMAGES_DIR}/{RAW_IMG}",
            QCOW2_IMG,
            marks=(pytest.mark.polarion("CNV-2008")),
        ),
        pytest.param(
            "cnv-2008",
            f"{CDI_IMAGES_DIR}/{QCOW2_IMG}",
            Images.Cirros.QCOW2_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-2008")),
        ),
        pytest.param(
            "cnv-2008",
            f"{CDI_IMAGES_DIR}/{QCOW2_IMG}",
            Images.Cirros.QCOW2_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2008")),
        ),
        pytest.param(
            "cnv-2008",
            f"{CDI_IMAGES_DIR}/{RAW_IMG}",
            Images.Cirros.RAW_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-2008")),
        ),
        pytest.param(
            "cnv-2008",
            f"{CDI_IMAGES_DIR}/{RAW_IMG}",
            Images.Cirros.RAW_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2008")),
        ),
        pytest.param(
            "cnv-2008",
            f"{CDI_IMAGES_DIR}/cirros_images/{Images.Cirros.RAW_IMG_GZ}",
            Images.Cirros.RAW_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-2008")),
        ),
        pytest.param(
            "cnv-2008",
            f"{CDI_IMAGES_DIR}/cirros_images/{Images.Cirros.RAW_IMG_XZ}",
            Images.Cirros.RAW_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2008")),
        ),
    ],
)
def test_successful_upload_with_supported_formats(
    storage_ns, tmpdir, dv_name, remote_name, local_name, default_client
):
    local_name = f"{tmpdir}/{local_name}"
    storage_utils.downloaded_image(remote_name=remote_name, local_name=local_name)
    with UploadDataVolume(
        name=dv_name,
        namespace=storage_ns.name,
        size="3Gi",
        storage_class=py_config["storage_defaults"]["storage_class"],
    ) as dv:
        dv.wait_for_status(status=UploadDataVolume.Status.UPLOAD_READY, timeout=180)
        with UploadTokenRequest(
            name=dv_name, namespace=storage_ns.name, client=default_client
        ) as utr:
            token = utr.create().status.token
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
            dv.wait()
            with storage_utils.create_vm_from_dv(dv=dv) as vm_dv:
                storage_utils.check_disk_count_in_vm(vm_dv)


@pytest.mark.polarion("CNV-2018")
def test_successful_upload_token_validity(storage_ns, tmpdir, default_client):
    dv_name = "cnv-2018"
    local_name = f"{tmpdir}/{QCOW2_IMG}"
    storage_utils.downloaded_image(
        remote_name=f"{CDI_IMAGES_DIR}/{QCOW2_IMG}", local_name=local_name
    )
    with UploadDataVolume(
        name=dv_name,
        namespace=storage_ns.name,
        size="3Gi",
        storage_class=py_config["storage_defaults"]["storage_class"],
    ) as dv:
        dv.wait_for_status(status=UploadDataVolume.Status.UPLOAD_READY, timeout=180)
        with UploadTokenRequest(
            name=dv_name, namespace=storage_ns.name, client=default_client
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
            name=dv_name, namespace=storage_ns.name, client=default_client
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
def test_successful_upload_token_expiry(storage_ns, tmpdir, default_client):
    dv_name = "cnv-2011"
    local_name = f"{tmpdir}/{QCOW2_IMG}"
    storage_utils.downloaded_image(
        remote_name=f"{CDI_IMAGES_DIR}/{QCOW2_IMG}", local_name=local_name
    )
    with UploadDataVolume(
        name=dv_name,
        namespace=storage_ns.name,
        size="3Gi",
        storage_class=py_config["storage_defaults"]["storage_class"],
    ) as dv:
        LOGGER.info("Wait for DV to be UploadReady")
        dv.wait_for_status(status=UploadDataVolume.Status.UPLOAD_READY, timeout=120)
        with UploadTokenRequest(
            name=dv_name, namespace=storage_ns.name, client=default_client
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


def upload_test(dv_name, storage_ns, local_name, default_client, size=None):
    """
    Upload test that is executed in parallel in with other tasks.
    """
    size = size or "3Gi"
    with UploadDataVolume(
        name=dv_name,
        namespace=storage_ns.name,
        size=size,
        storage_class=py_config["storage_defaults"]["storage_class"],
    ) as dv:
        LOGGER.info("Wait for DV to be UploadReady")
        dv.wait_for_status(status=UploadDataVolume.Status.UPLOAD_READY, timeout=300)
        with UploadTokenRequest(
            name=dv_name, namespace=storage_ns.name, client=default_client
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
def test_successful_concurrent_uploads(storage_ns, tmpdir, default_client):
    dvs_processes = []
    local_name = f"{tmpdir}/{QCOW2_IMG}"
    storage_utils.downloaded_image(
        remote_name=f"{CDI_IMAGES_DIR}/{QCOW2_IMG}", local_name=local_name
    )
    available_pv = PersistentVolume(storage_ns).max_available_pvs
    for dv in range(available_pv):
        dv_process = multiprocessing.Process(
            target=upload_test,
            args=(f"dv-{dv}", storage_ns, local_name, default_client),
        )
        dv_process.start()
        dvs_processes.append(dv_process)

    for dvs in dvs_processes:
        dvs.join()
        if dvs.exitcode != 0:
            raise pytest.fail("Creating DV exited with non-zero return code")


@pytest.mark.polarion("CNV-2017")
def test_successful_upload_missing_file_in_transit(storage_ns, tmpdir, default_client):
    dv_name = "cnv-2017"
    local_name = f"{tmpdir}/{RHEL8_QCOW2}"
    storage_utils.downloaded_image(
        remote_name=f"{RHEL8_IMAGES}/{RHEL8_QCOW2}", local_name=local_name
    )
    upload_process = multiprocessing.Process(
        target=upload_test,
        args=(dv_name, storage_ns, local_name, default_client, "10Gi"),
    )

    # Run process in parallel
    upload_process.start()

    # Ideally the file should be removed while the status of upload is 'UploadInProgress'.
    # However, 'UploadInProgress' status phase is never set.
    # Sleep for 15 seconds until https://bugzilla.redhat.com/show_bug.cgi?id=1725934 is fixed.
    # Once the bug is fixed, the below line needs to be uncommented and sleep should be removed.
    # DataVolume(dv_name, storage_ns).wait_for_status(status="UploadInProgress", timeout=300)
    time.sleep(15)
    sh.rm("-f", local_name)

    # Exit the completed processes
    upload_process.join()
