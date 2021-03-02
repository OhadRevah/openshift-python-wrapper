import pytest
from ocp_resources.package_manifest import PackageManifest


@pytest.fixture()
def hco_package_stable_channel_images(admin_client, hco_namespace):
    """
    Get a list of all images in the kubevirt-hyperconverged package on the stable channel
    """
    for package in PackageManifest.get(
        dyn_client=admin_client,
        namespace=hco_namespace,
        name="kubevirt-hyperconverged",
    ):
        for channel in package.instance.status.channels:
            if channel.name == "stable":
                return channel.currentCSVDesc["relatedImages"]


@pytest.mark.polarion("CNV-4751")
def test_immutable_image_using_sha(hco_package_stable_channel_images):
    """
    check all images of the stable channel on the kubevirt-hyperconverged Package Manifest.
    make sure all images have SHA256 in their string (this indicates they are immutable)
    """
    # verify all images contain "sha256" in their name. on failure this will be a list of images without "sha256"
    assert not list(
        filter(lambda image: "sha256" not in image, hco_package_stable_channel_images)
    )
