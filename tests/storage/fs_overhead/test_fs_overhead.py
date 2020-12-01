import math

import pytest
from utilities.infra import Images
from utilities.storage import ErrorMsg, downloaded_image, virtctl_upload_dv


FEDORA_IMAGE = Images.Fedora.FEDORA33_IMG
LOCAL_NAME = f"/tmp/{FEDORA_IMAGE}"
FEDORA_IMAGE_SIZE_GI = 4


def overhead_size_for_dv(image_size, overhead_value):
    """
    Calculate the size of the dv to include overhead and rounds up

    DV creation can be with a fraction only if the corresponding  mebibyte is an integer
    """
    dv_size = image_size / (1 - overhead_value) * 1024
    return f"{math.ceil(dv_size)}Mi"


@pytest.fixture(scope="module")
def local_fedora_image():
    downloaded_image(
        remote_name=f"{Images.Fedora.DIR}/{FEDORA_IMAGE}",
        local_name=LOCAL_NAME,
    )


@pytest.mark.polarion("CNV-5019")
def test_upload_with_enough_size_for_overhead(
    storage_class_matrix__module__,
    skip_block_volumemode_scope_module,
    namespace,
    local_fedora_image,
):
    with virtctl_upload_dv(
        name="cnv-5019",
        namespace=namespace.name,
        size=overhead_size_for_dv(
            image_size=FEDORA_IMAGE_SIZE_GI, overhead_value=0.055
        ),
        insecure=True,
        image_path=LOCAL_NAME,
        storage_class=[*storage_class_matrix__module__][0],
    ) as res:
        status, out = res
        assert status, out


@pytest.mark.polarion("CNV-5020")
def test_upload_with_same_size_as_image_should_fail(
    storage_class_matrix__module__,
    skip_block_volumemode_scope_module,
    namespace,
    local_fedora_image,
):
    with virtctl_upload_dv(
        name="cnv-5020",
        namespace=namespace.name,
        size=f"{FEDORA_IMAGE_SIZE_GI}Gi",
        insecure=True,
        image_path=LOCAL_NAME,
        storage_class=[*storage_class_matrix__module__][0],
    ) as res:
        status, out = res
        assert ErrorMsg.LARGER_PVC_REQUIRED in out
        assert not status
