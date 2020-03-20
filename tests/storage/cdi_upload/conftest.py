"""
CDI Import
"""

import pytest
import tests.storage.utils as storage_utils
from utilities.infra import Images


@pytest.fixture(scope="function")
def upload_file_path(request, tmpdir):
    params = request.param if hasattr(request, "param") else {}
    remote_image_dir = params.get("remote_image_dir", Images.Cirros.DIR)
    remote_image_name = params.get("remote_image_name", Images.Cirros.QCOW2_IMG)
    local_name = f"{tmpdir}/{remote_image_name}"
    storage_utils.downloaded_image(
        remote_name=f"{remote_image_dir}/{remote_image_name}", local_name=local_name,
    )
    yield local_name
