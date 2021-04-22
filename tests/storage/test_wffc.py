# -*- coding: utf-8 -*-

"""
HonorWaitForFirstConsumer test suite
"""

import logging

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.resource import ResourceEditor
from ocp_resources.storage_class import StorageClass

import tests.storage.utils as storage_utils
from utilities.constants import TIMEOUT_10MIN
from utilities.infra import Images, hco_cr_jsonpatch_annotations_dict
from utilities.storage import (
    cdi_feature_gate_list_with_added_feature,
    check_cdi_feature_gate_enabled,
    create_dv,
    downloaded_image,
    get_images_server_url,
    virtctl_upload_dv,
)
from utilities.virt import VirtualMachineForTests


pytestmark = pytest.mark.post_upgrade


LOGGER = logging.getLogger(__name__)

REMOTE_PATH = f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}"
DV_PARAMS = {
    "dv_name": "dv-wffc-tests",
    "storage_class": StorageClass.Types.HOSTPATH,
    "image": REMOTE_PATH,
    "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
}


@pytest.fixture(scope="module")
def enable_wffc_feature_gate(hyperconverged_resource_scope_module, cdi_config):
    honor_wffc = "HonorWaitForFirstConsumer"
    if check_cdi_feature_gate_enabled(feature=honor_wffc):
        yield
    else:
        # Feature gate wasn't enabled
        with ResourceEditor(
            patches={
                hyperconverged_resource_scope_module: hco_cr_jsonpatch_annotations_dict(
                    component="cdi",
                    path="featureGates",
                    value=cdi_feature_gate_list_with_added_feature(feature=honor_wffc),
                    op="replace",
                )
            },
        ):
            yield


def get_dv_template_dict(dv_name):
    return {
        "metadata": {
            "name": f"{dv_name}",
        },
        "spec": {
            "pvc": {
                "volumeMode": DataVolume.VolumeMode.FILE,
                "accessModes": [DataVolume.AccessMode.RWO],
                "resources": {"requests": {"storage": Images.Cirros.DEFAULT_DV_SIZE}},
                "storageClassName": StorageClass.Types.HOSTPATH,
            },
            "source": {
                "http": {"url": f"{get_images_server_url(schema='http')}{REMOTE_PATH}"}
            },
        },
    }


def add_dv_to_vm(vm, dv_name=None, template_dv=None):
    """
    Add another DV to a VM

    Can also be used to add a dataVolumeTemplate DV, just pass in template_dv param
    """
    if not (dv_name or template_dv):
        raise ValueError(
            "Either a dv_name (of an existing DV) or template_dv (dataVolumeTemplate spec) must be passed"
        )
    vm_instance = vm.instance.to_dict()
    template_spec = vm_instance["spec"]["template"]["spec"]
    dv_name = dv_name or template_dv["metadata"]["name"]
    patch = {
        "spec": {
            "template": {
                "spec": {
                    "domain": {
                        "devices": {
                            "disks": [
                                *template_spec["domain"]["devices"]["disks"],
                                {"disk": {"bus": "virtio"}, "name": dv_name},
                            ]
                        }
                    },
                    "volumes": [
                        *template_spec["volumes"],
                        {"name": dv_name, "dataVolume": {"name": dv_name}},
                    ],
                },
            },
        }
    }
    if template_dv:
        patch["spec"]["dataVolumeTemplates"] = [
            *vm_instance["spec"].setdefault("dataVolumeTemplates", []),
            template_dv,
        ]
    ResourceEditor(patches={vm: patch}).update()


@pytest.mark.parametrize(
    "data_volume_scope_function",
    [
        pytest.param(
            {**DV_PARAMS, **{"consume_wffc": True}},
            marks=pytest.mark.polarion("CNV-4371"),
        ),
    ],
    indirect=True,
)
def test_wffc_import_http_dv(
    skip_test_if_no_hpp_sc,
    skip_when_hpp_no_waitforfirstconsumer,
    enable_wffc_feature_gate,
    data_volume_scope_function,
):
    with storage_utils.create_vm_from_dv(
        dv=data_volume_scope_function, vm_name=data_volume_scope_function.name
    ) as vm_dv:
        storage_utils.check_disk_count_in_vm(vm=vm_dv)


@pytest.mark.polarion("CNV-4739")
def test_wffc_import_registry_dv(
    skip_test_if_no_hpp_sc,
    skip_when_hpp_no_waitforfirstconsumer,
    enable_wffc_feature_gate,
    namespace,
):
    dv_name = "cnv-4739"
    with create_dv(
        source="registry",
        dv_name=dv_name,
        namespace=namespace.name,
        url=f"docker://quay.io/kubevirt/{Images.Cirros.DISK_DEMO}",
        storage_class=StorageClass.Types.HOSTPATH,
        volume_mode=DataVolume.VolumeMode.FILE,
        consume_wffc=True,
    ) as dv:
        dv.wait()
        with storage_utils.create_vm_from_dv(dv=dv, vm_name=dv_name) as vm_dv:
            storage_utils.check_disk_count_in_vm(vm=vm_dv)


@pytest.mark.polarion("CNV-4741")
def test_wffc_upload_dv_via_token(
    skip_test_if_no_hpp_sc,
    skip_when_hpp_no_waitforfirstconsumer,
    enable_wffc_feature_gate,
    namespace,
    unprivileged_client,
    tmpdir,
):
    dv_name = "cnv-4741"
    local_name = f"{tmpdir}/{Images.Cirros.QCOW2_IMG}"
    downloaded_image(
        remote_name=REMOTE_PATH,
        local_name=local_name,
    )
    with storage_utils.upload_image_to_dv(
        dv_name=dv_name,
        storage_class=StorageClass.Types.HOSTPATH,
        volume_mode=DataVolume.VolumeMode.FILE,
        storage_ns_name=namespace.name,
        client=unprivileged_client,
        consume_wffc=True,
    ) as dv:
        storage_utils.upload_token_request(
            storage_ns_name=namespace.name, pvc_name=dv.pvc.name, data=local_name
        )
        dv.wait()
        with storage_utils.create_vm_from_dv(dv=dv, vm_name=dv_name) as vm_dv:
            storage_utils.check_disk_count_in_vm(vm=vm_dv)


@pytest.mark.polarion("CNV-4711")
def test_wffc_upload_dv_via_virtctl(
    skip_test_if_no_hpp_sc,
    skip_when_hpp_no_waitforfirstconsumer,
    enable_wffc_feature_gate,
    namespace,
    tmpdir,
):
    dv_name = "cnv-4711"
    local_name = f"{tmpdir}/{Images.Cirros.QCOW2_IMG}"
    downloaded_image(
        remote_name=REMOTE_PATH,
        local_name=local_name,
    )
    with virtctl_upload_dv(
        namespace=namespace.name,
        name=dv_name,
        size=Images.Cirros.DEFAULT_DV_SIZE,
        image_path=local_name,
        storage_class=StorageClass.Types.HOSTPATH,
        insecure=True,
        consume_wffc=True,
    ):
        dv = DataVolume(namespace=namespace.name, name=dv_name)
        dv.wait(timeout=60)
        with storage_utils.create_vm_from_dv(dv=dv, vm_name=dv_name) as vm_dv:
            storage_utils.check_disk_count_in_vm(vm=vm_dv)


@pytest.mark.parametrize(
    "data_volume_scope_function",
    [
        pytest.param(
            {**DV_PARAMS, **{"consume_wffc": True}},
            marks=pytest.mark.polarion("CNV-4379"),
        ),
    ],
    indirect=True,
)
def test_wffc_clone_dv(
    skip_test_if_no_hpp_sc,
    skip_when_hpp_no_waitforfirstconsumer,
    enable_wffc_feature_gate,
    data_volume_scope_function,
):
    with create_dv(
        source="pvc",
        dv_name="dv-target",
        namespace=data_volume_scope_function.namespace,
        size=data_volume_scope_function.size,
        source_pvc=data_volume_scope_function.name,
        storage_class=data_volume_scope_function.storage_class,
        volume_mode=data_volume_scope_function.volume_mode,
        access_modes=data_volume_scope_function.access_modes,
        consume_wffc=True,
    ) as cdv:
        cdv.wait(timeout=TIMEOUT_10MIN)
        with storage_utils.create_vm_from_dv(dv=cdv, vm_name=cdv.name) as vm_dv:
            storage_utils.check_disk_count_in_vm(vm=vm_dv)


@pytest.mark.parametrize(
    "data_volume_scope_function",
    [
        pytest.param(
            {**DV_PARAMS, **{"consume_wffc": False}},
            marks=pytest.mark.polarion("CNV-4742"),
        ),
    ],
    indirect=True,
)
def test_wffc_add_dv_to_vm_with_data_volume_template(
    skip_test_if_no_hpp_sc,
    skip_when_hpp_no_waitforfirstconsumer,
    enable_wffc_feature_gate,
    namespace,
    data_volume_scope_function,
):
    with VirtualMachineForTests(
        name="cnv-4742-vm",
        namespace=namespace.name,
        data_volume_template=get_dv_template_dict(dv_name="template-dv"),
        memory_requests=Images.Cirros.DEFAULT_MEMORY_SIZE,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running(timeout=120)
        storage_utils.check_disk_count_in_vm(vm=vm)
        # Add DV
        vm.stop(wait=True)
        add_dv_to_vm(vm=vm, dv_name=data_volume_scope_function.name)
        # Check DV was added
        vm.start(wait=True)
        vm.vmi.wait_until_running(timeout=120)
        storage_utils.check_disk_count_in_vm(vm=vm)


@pytest.mark.polarion("CNV-4743")
def test_wffc_vm_with_two_data_volume_templates(
    skip_test_if_no_hpp_sc,
    skip_when_hpp_no_waitforfirstconsumer,
    enable_wffc_feature_gate,
    namespace,
):
    with VirtualMachineForTests(
        name="cnv-4743-vm",
        namespace=namespace.name,
        data_volume_template=get_dv_template_dict(dv_name="template-dv-1"),
        memory_requests=Images.Cirros.DEFAULT_MEMORY_SIZE,
    ) as vm:
        add_dv_to_vm(vm=vm, template_dv=get_dv_template_dict(dv_name="template-dv-2"))
        vm.start(wait=True)
        vm.vmi.wait_until_running(timeout=120)
        storage_utils.check_disk_count_in_vm(vm=vm)
