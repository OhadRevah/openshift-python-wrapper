import pytest
from resources.package_manifest import PackageManifest


@pytest.fixture()
def images_list(admin_client, hco_namespace):
    """
    Get package from PackageManifest.
    """
    image_list = []
    for package in PackageManifest.get(
        dyn_client=admin_client, namespace=hco_namespace
    ):
        if package.name == "kubevirt-hyperconverged":
            for channel in package.instance.status.channels:
                if 2.3 < float(channel.name):
                    image_list += channel.currentCSVDesc["relatedImages"]

    return image_list


@pytest.mark.polarion("CNV-4751")
def test_immutable_image_using_sha(images_list):
    """
    Retrieve images from Package Manifest.
    Check links contains SHA256 string in those images.
    """
    assert not [image for image in images_list if "sha256" not in image]
