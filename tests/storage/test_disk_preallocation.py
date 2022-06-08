# -*- coding: utf-8 -*-

"""
CDI disk preallocation test suite
"""

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.resource import NamespacedResource

from utilities.constants import Images
from utilities.hco import (
    ResourceEditorValidateHCOReconcile,
    hco_cr_jsonpatch_annotations_dict,
)


pytestmark = pytest.mark.post_upgrade


@pytest.fixture(scope="module")
def cdi_preallocation_enabled(hyperconverged_resource_scope_module):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_module: hco_cr_jsonpatch_annotations_dict(
                component="cdi",
                path="preallocation",
                value=True,
            )
        },
    ):
        yield


def assert_preallocation_requested_annotation(pvc, status):
    preallocation_requested_annotation = (
        f"{NamespacedResource.ApiGroup.CDI_KUBEVIRT_IO}/storage.preallocation.requested"
    )
    assert (
        pvc.instance.metadata.annotations.get(preallocation_requested_annotation)
        == status
    ), f"'{preallocation_requested_annotation}' should be '{status}'"


def assert_preallocation_annotation(pvc, res):
    preallocation_annotation = (
        f"{NamespacedResource.ApiGroup.CDI_KUBEVIRT_IO}/storage.preallocation"
    )
    assert (
        pvc.instance.metadata.annotations.get(preallocation_annotation) == res
    ), f"'{preallocation_annotation}' should be '{res}'"


@pytest.mark.sno
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cnv-5512",
                "image": f"{Images.Rhel.DIR}/{Images.Rhel.RHEL8_2_IMG}",
                "dv_size": Images.Rhel.DEFAULT_DV_SIZE,
                "volume_mode": DataVolume.VolumeMode.FILE,
                "access_modes": DataVolume.AccessMode.RWO,
                "preallocation": True,
            },
            marks=(pytest.mark.polarion("CNV-5512")),
        ),
    ],
    indirect=True,
)
def test_preallocation_dv(
    data_volume_multi_storage_scope_function,
):
    """
    Test that preallocation of the kubevirt disk is enabled via an API in the DataVolume spec
    """
    pvc = data_volume_multi_storage_scope_function.pvc
    assert_preallocation_requested_annotation(pvc=pvc, status="true")
    assert_preallocation_annotation(pvc=pvc, res="true")


@pytest.mark.sno
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_module",
    [
        pytest.param(
            {
                "dv_name": "cnv-5513",
                "source": "http",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": "100Mi",
                "volume_mode": DataVolume.VolumeMode.FILE,
                "access_modes": DataVolume.AccessMode.RWO,
            },
            marks=pytest.mark.polarion("CNV-5513"),
        ),
    ],
    indirect=True,
)
def test_preallocation_globally_dv_spec_without_preallocation(
    cdi_preallocation_enabled,
    data_volume_multi_storage_scope_module,
):
    """
    Test that preallocation can be also turned on for all DataVolumes with the CDI CR entry.
    When create a general DataVolume without preallocation on DataVolume's spec, CDI would look into CDI CR.
    """
    pvc = data_volume_multi_storage_scope_module.pvc
    assert_preallocation_requested_annotation(pvc=pvc, status="true")


@pytest.mark.sno
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cnv-5741",
                "source": "http",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": "100Mi",
                "volume_mode": DataVolume.VolumeMode.FILE,
                "access_modes": DataVolume.AccessMode.RWO,
                "preallocation": False,
            },
            marks=pytest.mark.polarion("CNV-5741"),
        ),
    ],
    indirect=True,
)
def test_preallocation_globally_dv_spec_with_preallocation_false(
    cdi_preallocation_enabled,
    data_volume_multi_storage_scope_function,
):
    """
    When create a general DataVolume with preallocation set false on DataVolume's spec, preallocation will not be used.
    It won't take CDI CR into account because it is explicit in the DV.
    """
    pvc = data_volume_multi_storage_scope_function.pvc
    assert_preallocation_requested_annotation(pvc=pvc, status="false")


@pytest.mark.sno
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cnv-5737",
                "source": "blank",
                "dv_size": "100Mi",
                "volume_mode": DataVolume.VolumeMode.FILE,
                "access_modes": DataVolume.AccessMode.RWO,
                "preallocation": True,
            },
            marks=pytest.mark.polarion("CNV-5737"),
        ),
    ],
    indirect=True,
)
def test_preallocation_for_blank_dv(
    data_volume_multi_storage_scope_function,
):
    """
    Test that preallocation for blank disk should be supported
    """
    pvc = data_volume_multi_storage_scope_function.pvc
    assert_preallocation_requested_annotation(pvc=pvc, status="true")
    assert_preallocation_annotation(pvc=pvc, res="true")
