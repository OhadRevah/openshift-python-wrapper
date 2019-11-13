# -*- coding: utf-8 -*-

"""
Upload using virtctl
"""

import logging

import pytest
import tests.storage.utils as storage_utils
from openshift.dynamic.exceptions import NotFoundError
from pytest_testconfig import config as py_config
from resources.persistent_volume_claim import PersistentVolumeClaim
from resources.route import Route


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
def test_successful_virtctl_upload_no_route(
    storage_ns, tmpdir, uploadproxy_route_deleted
):
    route = Route(name="cdi-uploadproxy", namespace=py_config["hco_namespace"])
    with pytest.raises(NotFoundError):
        route.instance

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


@pytest.mark.polarion("CNV-2217")
def test_image_upload_with_overridden_url(
    storage_ns, tmpdir, new_route_created, cdi_config_upload_proxy_overridden
):
    pvc_name = "cnv-2217"
    local_name = f"{tmpdir}/{QCOW2_IMG}"
    storage_utils.downloaded_image(
        remote_name=f"{CDI_IMAGES_DIR}/{QCOW2_IMG}", local_name=local_name
    )
    virtctl_upload = storage_utils.virtctl_upload(
        namespace=storage_ns.name,
        pvc_name=pvc_name,
        pvc_size="1Gi",
        image_path=local_name,
    )
    assert virtctl_upload
    LOGGER.info(f"{virtctl_upload}")
    assert PersistentVolumeClaim(name=pvc_name, namespace=storage_ns.name).bound()
