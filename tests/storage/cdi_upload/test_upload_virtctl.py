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
from utilities.infra import Images


LOGGER = logging.getLogger(__name__)


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
    virtctl_upload = storage_utils.virtctl_upload(
        namespace=namespace.name,
        pvc_name=pvc_name,
        pvc_size="1Gi",
        image_path=local_name,
        insecure=True,
    )
    assert virtctl_upload
    LOGGER.info(f"{virtctl_upload}")
    assert PersistentVolumeClaim(name=pvc_name, namespace=namespace.name).bound()


@pytest.mark.destructive
@pytest.mark.polarion("CNV-2191")
def test_successful_virtctl_upload_no_route(
    namespace, tmpdir, uploadproxy_route_deleted
):
    route = Route(name="cdi-uploadproxy", namespace=py_config["hco_namespace"])
    with pytest.raises(NotFoundError):
        route.instance

    local_name = f"{tmpdir}/{Images.Cdi.QCOW2_IMG}"
    storage_utils.downloaded_image(
        remote_name=f"{Images.Cdi.DIR}/{Images.Cdi.QCOW2_IMG}", local_name=local_name
    )
    pvc_name = "cnv-2191"
    virtctl_upload, virtctl_upload_out = storage_utils.virtctl_upload(
        namespace=namespace.name,
        pvc_name=pvc_name,
        pvc_size="1Gi",
        image_path=local_name,
        insecure=True,
    )
    LOGGER.info(f"{virtctl_upload_out}")
    assert (
        virtctl_upload is False
    ), f"virtctl image-upload command successful, must fail with a non-zero rc"


@pytest.mark.polarion("CNV-2217")
def test_image_upload_with_overridden_url(
    namespace, tmpdir, new_route_created, cdi_config_upload_proxy_overridden
):
    pvc_name = "cnv-2217"
    local_name = f"{tmpdir}/{Images.Cdi.QCOW2_IMG}"
    storage_utils.downloaded_image(
        remote_name=f"{Images.Cdi.DIR}/{Images.Cdi.QCOW2_IMG}", local_name=local_name
    )
    virtctl_upload = storage_utils.virtctl_upload(
        namespace=namespace.name,
        pvc_name=pvc_name,
        pvc_size="1Gi",
        image_path=local_name,
        insecure=True,
    )
    assert virtctl_upload
    LOGGER.info(f"{virtctl_upload}")
    assert PersistentVolumeClaim(name=pvc_name, namespace=namespace.name).bound()


@pytest.mark.polarion("CNV-3031")
def test_virtctl_image_upload_with_ca(skip_no_reencrypt_route, tmpdir, namespace):
    local_path = f"{tmpdir}/{Images.Cdi.QCOW2_IMG}"
    storage_utils.downloaded_image(
        remote_name=f"{Images.Cdi.DIR}/{Images.Cdi.QCOW2_IMG}", local_name=local_path
    )
    pvc_name = "cnv-3031"
    res, out = storage_utils.virtctl_upload(
        namespace=namespace.name,
        pvc_name=pvc_name,
        pvc_size="1Gi",
        image_path=local_path,
    )
    LOGGER.info(out)
    assert res
    pvc = PersistentVolumeClaim(namespace=namespace.name, name=pvc_name)
    assert pvc.bound()
