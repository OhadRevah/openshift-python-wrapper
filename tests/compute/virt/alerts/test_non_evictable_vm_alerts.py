"""
Create non-evictable VM with RWO Storage and evictionStrategy=True that should fire the VMCannotBeEvicted alert
"""

import pytest
from ocp_resources.datavolume import DataVolume
from pytest_testconfig import py_config

from tests.os_params import FEDORA_LATEST_LABELS
from utilities.constants import Images


@pytest.mark.parametrize(
    "data_volume_scope_function, vm_from_template_with_existing_dv",
    [
        pytest.param(
            {
                "dv_name": "non-evictable-dv",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "storage_class": py_config["default_storage_class"],
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
                "access_modes": DataVolume.AccessMode.RWO,
            },
            {
                "vm_name": "non-evictable-vm",
                "template_labels": FEDORA_LATEST_LABELS,
                "ssh": False,
                "guest_agent": False,
                "eviction": True,
            },
            marks=pytest.mark.polarion("CNV-7484"),
        ),
    ],
    indirect=True,
)
def test_non_evictable_vm_fired_alert(
    prometheus,
    data_volume_scope_function,
    vm_from_template_with_existing_dv,
):
    prometheus.alert_sampler(alert="VMCannotBeEvicted")
