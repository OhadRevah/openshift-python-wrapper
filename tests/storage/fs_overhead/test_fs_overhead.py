import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.storage_class import StorageClass

from tests.storage.utils import (
    get_importer_pod,
    storage_params,
    wait_for_importer_container_message,
)
from utilities.constants import TIMEOUT_5MIN, Images
from utilities.storage import (
    ErrorMsg,
    check_upload_virtctl_result,
    create_dv,
    downloaded_image,
    get_images_server_url,
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


@pytest.fixture(scope="module")
def data_volume_with_same_size_as_image(
    skip_block_volumemode_scope_module,
    namespace,
    storage_class_matrix__module__,
):
    with create_dv(
        source="http",
        dv_name="dv-cnv-5020",
        namespace=namespace.name,
        url=f"{get_images_server_url(schema='http')}{Images.Fedora.DIR}/{FEDORA_IMAGE}",
        size=f"{FEDORA_IMAGE_SIZE_GI}Gi",
        **storage_params(storage_class_matrix=storage_class_matrix__module__),
        api_name="pvc",
    ) as dv:
        dv.wait_for_status(
            status=DataVolume.Status.IMPORT_IN_PROGRESS, timeout=TIMEOUT_5MIN
        )
        yield dv


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
        check_upload_virtctl_result(result=res)


@pytest.mark.polarion("CNV-5020")
def test_import_with_same_size_as_image_should_fail(
    namespace,
    admin_client,
    data_volume_with_same_size_as_image,
):
    """
    Import dv of the same size as image size to Filesystem volume mode
    without considering fs overhead should fail when using "pvc" api.
    Although it will succeed when using "storage" api because of the auto-resize feature.
    """
    importer_pod = get_importer_pod(dyn_client=admin_client, namespace=namespace.name)
    wait_for_importer_container_message(
        importer_pod=importer_pod,
        msg=ErrorMsg.LARGER_PVC_REQUIRED,
    )


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
        check_upload_virtctl_result(result=res)
