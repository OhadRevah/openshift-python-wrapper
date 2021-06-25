"""
CDI Import
"""

import logging
import os
import re
import subprocess

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


@pytest.fixture(scope="session")
def skip_router_wildcard_cert_not_trusted(admin_client):
    trust_store_dir = "/etc/pki/ca-trust/source/anchors/"
    wildcard_hostname = (
        f"*.apps{re.search(r'.*api(.*):.*', admin_client.configuration.host).group(1)}"
    )
    extensions = (".crt", ".cer", "pem")

    for file in os.listdir(trust_store_dir):
        if file.endswith(extensions):
            try:
                output = subprocess.check_output(
                    f"openssl x509 -in {os.path.join(trust_store_dir, file)} -noout -text",
                    shell=True,
                )
                if wildcard_hostname in output.decode("utf-8"):
                    return
            except subprocess.CalledProcessError as e:
                # Ignore errors, local system can have corrupt certs
                # If needed cert exists, we can proceed
                LOGGER.warning(e.output)

    pytest.skip(
        msg="Skip testing. Wildcard router certificate not in systems trust store."
    )


@pytest.fixture()
def download_specified_image(request, tmpdir_factory):
    local_path = tmpdir_factory.mktemp("cdi_upload").join(
        request.param.get("image_file")
    )
    downloaded_image(remote_name=request.param.get("image_path"), local_name=local_path)
    return local_path
