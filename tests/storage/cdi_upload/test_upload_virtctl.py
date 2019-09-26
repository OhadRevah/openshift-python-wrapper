# -*- coding: utf-8 -*-

"""
Upload using virtctl
"""

import logging

import pytest
import tests.storage.utils as storage_utils
from resources.persistent_volume_claim import PersistentVolumeClaim


LOGGER = logging.getLogger(__name__)
CDI_IMAGES_DIR = "cdi-test-images"
QCOW2_IMG = "cirros-qcow2.img"


@pytest.mark.polarion("CNV-2192")
def test_successful_virtctl_upload_no_url(storage_ns, tmpdir):
    local_name = f"{tmpdir}/{QCOW2_IMG}"
    storage_utils.downloaded_image(
        remote_name=f"{CDI_IMAGES_DIR}/{QCOW2_IMG}", local_name=local_name
    )
    pvc_name = "cnv-2192"
    virtctl_upload = storage_utils.virtctl_upload(
        namespace=storage_ns.name,
        pvc_name=pvc_name,
        pvc_size="1Gi",
        image_path=local_name,
    )
    assert virtctl_upload
    LOGGER.info(f"{virtctl_upload}")
    assert PersistentVolumeClaim(name=pvc_name, namespace=storage_ns.name).bound()


@pytest.mark.polarion("CNV-2191")
def test_successful_virtctl_upload_no_route(storage_ns, tmpdir):
    local_name = f"{tmpdir}/{QCOW2_IMG}"
    storage_utils.downloaded_image(
        remote_name=f"{CDI_IMAGES_DIR}/{QCOW2_IMG}", local_name=local_name
    )
    pvc_name = "cnv-2191"
    virtctl_upload, virtctl_upload_out = storage_utils.virtctl_upload(
        namespace=storage_ns.name,
        pvc_name=pvc_name,
        pvc_size="1Gi",
        image_path=local_name,
    )
    LOGGER.info(f"{virtctl_upload_out}")
    assert (
        virtctl_upload is False
    ), f"virtctl image-upload command successful, must fail with a non-zero rc"
