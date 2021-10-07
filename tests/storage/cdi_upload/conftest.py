"""
CDI Import
"""

import logging

import pytest

from utilities.constants import Images
from utilities.storage import downloaded_image


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="function")
def upload_file_path(request, tmpdir):
    params = request.param if hasattr(request, "param") else {}
    remote_image_dir = params.get("remote_image_dir", Images.Cirros.DIR)
    remote_image_name = params.get("remote_image_name", Images.Cirros.QCOW2_IMG)
    local_name = f"{tmpdir}/{remote_image_name}"
    downloaded_image(
        remote_name=f"{remote_image_dir}/{remote_image_name}",
        local_name=local_name,
    )
    yield local_name


@pytest.fixture()
def download_specified_image(request, tmpdir_factory):
    local_path = tmpdir_factory.mktemp("cdi_upload").join(
        request.param.get("image_file")
    )
    downloaded_image(remote_name=request.param.get("image_path"), local_name=local_path)
    return local_path
