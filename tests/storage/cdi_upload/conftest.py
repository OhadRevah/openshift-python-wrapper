"""
CDI Import
"""

import base64
import logging
import os

import pytest
from ocp_resources.secret import Secret

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


@pytest.fixture()
def router_cert_secret(admin_client):
    return list(
        Secret.get(
            dyn_client=admin_client,
            name="router-certs-default",
            namespace="openshift-ingress",
        )
    )[0]


@pytest.fixture()
def enabled_ca(tmpdir, router_cert_secret):
    update_ca_trust_command = "sudo update-ca-trust"
    router_cert_name = "router.crt"
    router_cert_path = f"{tmpdir}/{router_cert_name}"
    ca_path = "/etc/pki/ca-trust/source/anchors/"
    with open(router_cert_path, "w") as the_file:
        the_file.write(
            (
                base64.standard_b64decode(router_cert_secret.instance.data["tls.crt"])
            ).decode("utf-8")
        )
    # copy to the trusted secure list and update
    os.popen(f"sudo cp {router_cert_path} {ca_path}")
    os.popen(update_ca_trust_command)
    yield
    os.popen(f"sudo rm {ca_path}{router_cert_name}")
    os.popen(update_ca_trust_command)
