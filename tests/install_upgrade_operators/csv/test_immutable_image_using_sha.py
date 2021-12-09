import pytest

from tests.install_upgrade_operators.utils import get_package_manifest_images


pytestmark = pytest.mark.sno


@pytest.mark.polarion("CNV-4751")
def test_immutable_image_using_sha(skip_if_nightly_channel, admin_client):
    """
    check all images of the stable channel on the kubevirt-hyperconverged Package Manifest.
    make sure all images have SHA256 in their string (this indicates they are immutable)
    """
    # verify all images contain "sha256" in their name. on failure this will be a list of images without "sha256"
    assert not list(
        filter(
            lambda image: "sha256" not in image,
            get_package_manifest_images(admin_client=admin_client),
        )
    )
