# -*- coding: utf-8 -*-

"""
Clone tests
"""

import pytest
import utilities.storage
from tests.storage import utils
from utilities.infra import Images


@pytest.mark.parametrize(
    "data_volume_scope_class",
    [
        {
            "dv_name": "dv-source",
            "image": f"{Images.Windows.DIR}/{Images.Windows.WIN19_IMG}",
        },
    ],
    indirect=True,
)
@pytest.mark.polarion("CNV-1892")
def test_successful_clone_of_large_image(
    skip_upstream, storage_class_matrix, namespace, data_volume_scope_class,
):
    storage_class = [*storage_class_matrix][0]
    with utilities.storage.create_dv(
        source="pvc",
        dv_name="dv-target",
        namespace=namespace.name,
        size=data_volume_scope_class.size,
        storage_class=storage_class,
        volume_mode=storage_class_matrix[storage_class]["volume_mode"],
    ) as cdv:
        cdv.wait(timeout=1500)
        pvc = cdv.pvc
        assert pvc.bound()


@pytest.mark.parametrize(
    "data_volume_scope_class",
    [
        {
            "dv_name": "dv-source",
            "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
            "dv_size": "10Gi",
        },
    ],
    indirect=True,
)
@pytest.mark.polarion("CNV-2148")
def test_successful_vm_restart_with_cloned_dv(
    skip_upstream, storage_class_matrix, namespace, data_volume_scope_class,
):
    storage_class = [*storage_class_matrix][0]
    with utilities.storage.create_dv(
        source="pvc",
        dv_name="dv-target",
        namespace=namespace.name,
        size=data_volume_scope_class.size,
        storage_class=storage_class,
        volume_mode=storage_class_matrix[storage_class]["volume_mode"],
    ) as cdv:
        cdv.wait(timeout=600)
        with utils.create_vm_from_dv(dv=cdv) as vm_dv:
            utils.check_disk_count_in_vm(vm=vm_dv)
            vm_dv.restart(timeout=300, wait=True)
