import logging
import time

import pytest
from kubernetes.client.rest import ApiException
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.template import Template
from pytest_testconfig import config as py_config

from tests.storage import utils
from utilities import console
from utilities.storage import (
    ErrorMsg,
    create_dv,
    data_volume_template_dict,
    get_images_external_http_server,
)
from utilities.virt import VirtualMachineForTestsFromTemplate, wait_for_console


LOGGER = logging.getLogger(__name__)
LATEST_RHEL_IMAGE = py_config["latest_rhel_version"]["image_path"]
RHEL_IMAGE_SIZE = py_config["latest_rhel_version"]["dv_size"]
GOLDEN_IMAGES_NAMESPACE = py_config["golden_images_namespace"]


DV_PARAM = {
    "dv_name": "golden-image-dv",
    "image": LATEST_RHEL_IMAGE,
    "dv_namespace": GOLDEN_IMAGES_NAMESPACE,
    "dv_size": RHEL_IMAGE_SIZE,
    "storage_class": py_config["default_storage_class"],
}


@pytest.mark.polarion("CNV-4755")
def test_regular_user_cant_create_dv_in_ns(
    golden_images_namespace,
    unprivileged_client,
):
    LOGGER.info(
        "Try as a regular user, to create a DV in golden image NS and receive the proper error"
    )
    with pytest.raises(
        ApiException,
        match=ErrorMsg.CANNOT_CREATE_RESOURCE,
    ):
        with create_dv(
            client=unprivileged_client,
            dv_name="cnv-4755",
            namespace=golden_images_namespace.name,
            url=f"{get_images_external_http_server()}{LATEST_RHEL_IMAGE}",
            size=RHEL_IMAGE_SIZE,
            storage_class=py_config["default_storage_class"],
            volume_mode=py_config["default_volume_mode"],
        ):
            return


@pytest.mark.parametrize(
    "data_volume_scope_module",
    [
        pytest.param(DV_PARAM, marks=pytest.mark.polarion("CNV-4756")),
    ],
    indirect=True,
)
def test_regular_user_cant_delete_dv_from_cloned_dv(
    golden_images_namespace,
    unprivileged_client,
    data_volume_scope_module,
):
    LOGGER.info(
        "Try as a regular user, to delete a dv from golden image NS and receive the proper error"
    )
    with pytest.raises(
        ApiException,
        match=ErrorMsg.CANNOT_DELETE_RESOURCE,
    ):
        DataVolume(
            name=data_volume_scope_module.name,
            namespace=golden_images_namespace.name,
            client=unprivileged_client,
        ).delete()


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": f"golden-image-dv-{time.time()}".replace(".", "-"),
                "image": LATEST_RHEL_IMAGE,
                "dv_namespace": GOLDEN_IMAGES_NAMESPACE,
                "dv_size": RHEL_IMAGE_SIZE,
            },
            marks=pytest.mark.polarion("CNV-4757"),
        ),
    ],
    indirect=True,
)
def test_regular_user_can_create_vm_from_cloned_dv(
    unprivileged_client,
    worker_node1,
    namespace,
    data_volume_multi_storage_scope_function,
):
    LOGGER.info(
        "Clone a DV from the golden images NS to a new NS and create a VM using the cloned DV"
    )
    with VirtualMachineForTestsFromTemplate(
        name="vm-for-test",
        namespace=namespace.name,
        client=unprivileged_client,
        labels=Template.generate_template_labels(
            **py_config["latest_rhel_version"]["template_labels"]
        ),
        data_volume_template=data_volume_template_dict(
            target_dv_name=f"user-dv-{time.time()}".replace(".", "-"),
            target_dv_namespace=namespace.name,
            source_dv=data_volume_multi_storage_scope_function,
            worker_node=worker_node1,
        ),
    ) as vm:
        vm.start(wait=True, timeout=1200)
        vm.vmi.wait_until_running(timeout=300)
        wait_for_console(vm=vm, console_impl=console.RHEL)


@pytest.mark.parametrize(
    "data_volume_scope_module",
    [
        pytest.param(DV_PARAM, marks=pytest.mark.polarion("CNV-4758")),
    ],
    indirect=True,
)
def test_regular_user_can_list_all_pvc_in_ns(
    golden_images_namespace,
    unprivileged_client,
    data_volume_scope_module,
):
    LOGGER.info(
        "Make sure regulr user have permissions to view PVC's in golden image NS"
    )
    assert list(
        PersistentVolumeClaim.get(
            dyn_client=unprivileged_client,
            namespace=golden_images_namespace.name,
            field_selector=f"metadata.name=={data_volume_scope_module.name}",
        )
    )


@pytest.mark.parametrize(
    "data_volume_scope_module",
    [
        pytest.param(DV_PARAM, marks=pytest.mark.polarion("CNV-4760")),
    ],
    indirect=True,
)
def test_regular_user_cant_clone_dv_in_ns(
    golden_images_namespace,
    unprivileged_client,
    data_volume_scope_module,
):
    LOGGER.info(
        "Try to clone a DV in the golden image NS and fail with the proper message"
    )
    with pytest.raises(
        ApiException,
        match=ErrorMsg.CANNOT_CREATE_RESOURCE,
    ):
        with create_dv(
            dv_name="cloned-dv",
            namespace=golden_images_namespace.name,
            source="pvc",
            size=data_volume_scope_module.size,
            source_pvc=data_volume_scope_module.pvc.name,
            source_namespace=data_volume_scope_module.name,
            client=unprivileged_client,
            storage_class=data_volume_scope_module.storage_class,
            volume_mode=data_volume_scope_module.volume_mode,
        ):
            return


@pytest.mark.polarion("CNV-5275")
def test_regular_user_can_create_dv_in_ns_given_proper_rolebinding(
    golden_images_namespace,
    golden_images_edit_rolebinding,
    unprivileged_client,
    storage_class_matrix__function__,
):
    LOGGER.info(
        "Once a proper RoleBinding created, that use the os-images.kubevirt.io:edit\
        ClusterRole, a regular user can create a DV in the golden image NS.",
    )
    with create_dv(
        client=unprivileged_client,
        dv_name="cnv-5275",
        namespace=golden_images_namespace.name,
        url=f"{get_images_external_http_server()}{LATEST_RHEL_IMAGE}",
        size=RHEL_IMAGE_SIZE,
        **utils.storage_params(storage_class_matrix=storage_class_matrix__function__),
    ) as dv:
        dv.wait_for_status(status=dv.Status.SUCCEEDED, timeout=1200)
