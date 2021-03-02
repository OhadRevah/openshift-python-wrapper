# -*- coding: utf-8 -*-

"""
CDI disk preallocation test suite
"""

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.resource import NamespacedResource, ResourceEditor

from utilities.infra import (
    BUG_STATUS_CLOSED,
    Images,
    get_bug_status,
    get_bugzilla_connection_params,
)


@pytest.fixture(scope="module")
def cdi_preallocation_enabled(cdi):
    with ResourceEditor(patches={cdi: {"spec": {"config": {"preallocation": True}}}}):
        yield


@pytest.fixture(scope="module")
def cdi_filesystemoverhead_set(cdi):
    with ResourceEditor(
        patches={cdi: {"spec": {"config": {"filesystemOverhead": {"global": "0.055"}}}}}
    ):
        yield


def assert_preallocation_requested_annotation(pvc, status):
    # TODO: Once bug 1926119 fixed, we will automatically stop sending the typo
    preallocation_requested = (
        "storage.preallocacation.requested"
        if get_bug_status(
            bugzilla_connection_params=get_bugzilla_connection_params(), bug=1926119
        )
        not in BUG_STATUS_CLOSED
        else "storage.preallocation.requested"
    )
    preallocation_requested_annotation = (
        f"{NamespacedResource.ApiGroup.CDI_KUBEVIRT_IO}/{preallocation_requested}"
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
    cdi_filesystemoverhead_set,
    data_volume_multi_storage_scope_function,
):
    """
    Test that preallocation of the kubevirt disk is enabled via an API in the DataVolume spec
    """
    pvc = data_volume_multi_storage_scope_function.pvc
    assert_preallocation_requested_annotation(pvc=pvc, status="true")
    assert_preallocation_annotation(pvc=pvc, res="true")


@pytest.mark.bugzilla(
    1927746, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)
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
    cdi_filesystemoverhead_set,
    data_volume_multi_storage_scope_module,
):
    """
    Test that preallocation can be also turned on for all DataVolumes with the CDI CR entry.
    When create a general DataVolume without preallocation on DataVolume's spec, CDI would look into CDI CR.
    """
    pvc = data_volume_multi_storage_scope_module.pvc
    assert_preallocation_requested_annotation(pvc=pvc, status="true")


@pytest.mark.bugzilla(
    1927746, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)
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
    cdi_filesystemoverhead_set,
    data_volume_multi_storage_scope_function,
):
    """
    When create a general DataVolume with preallocation set false on DataVolume's spec, preallocation will not be used.
    It won't take CDI CR into account because it is explicit in the DV.
    """
    pvc = data_volume_multi_storage_scope_function.pvc
    assert_preallocation_requested_annotation(pvc=pvc, status="false")


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
    cdi_filesystemoverhead_set,
    data_volume_multi_storage_scope_function,
):
    """
    Test that preallocation for blank disk should be supported
    """
    pvc = data_volume_multi_storage_scope_function.pvc
    assert_preallocation_requested_annotation(pvc=pvc, status="true")
    assert_preallocation_annotation(pvc=pvc, res="true")
