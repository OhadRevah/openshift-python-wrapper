import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.storage_class import StorageClass

from utilities.infra import Images
from utilities.storage import (
    ErrorMsg,
    downloaded_image,
    overhead_size_for_dv,
    virtctl_upload_dv,
)


pytestmark = pytest.mark.post_upgrade


FEDORA_IMAGE = Images.Fedora.FEDORA33_IMG
LOCAL_NAME = f"/tmp/{FEDORA_IMAGE}"
FEDORA_IMAGE_SIZE_GI = 4


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
    default_fs_overhead,
):
    with virtctl_upload_dv(
        name="cnv-5019",
        namespace=namespace.name,
        size=overhead_size_for_dv(
            image_size=FEDORA_IMAGE_SIZE_GI, overhead_value=default_fs_overhead
        ),
        insecure=True,
        image_path=LOCAL_NAME,
        storage_class=[*storage_class_matrix__module__][0],
    ) as res:
        status, out, _ = res
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
        status, out, _ = res
        assert ErrorMsg.LARGER_PVC_REQUIRED in out
        assert not status


@pytest.mark.polarion("CNV-5507")
def test_fs_overhead_dont_affect_block_volume_mode(
    skip_test_if_no_ocs_sc,
    namespace,
    local_fedora_image,
):
    with virtctl_upload_dv(
        name="cnv-5507",
        namespace=namespace.name,
        size=f"{FEDORA_IMAGE_SIZE_GI}Gi",
        insecure=True,
        image_path=LOCAL_NAME,
        storage_class=StorageClass.Types.CEPH_RBD,
        volume_mode=DataVolume.VolumeMode.BLOCK,
    ) as res:
        status, out, _ = res
        assert status, out