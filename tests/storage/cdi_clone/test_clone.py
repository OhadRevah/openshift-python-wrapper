# -*- coding: utf-8 -*-

"""
Clone tests
"""

import pytest
from pytest_testconfig import config as py_config
from tests.storage import utils
from tests.storage.utils import CDI_IMAGES_DIR
from utilities.infra import get_images_external_http_server


WIN_IMAGES_DIR = "window_qcow2_images"
QCOW2_IMG = "cirros-qcow2.img"
WIN10_QCOW2 = "win_10.qcow2"


@pytest.mark.polarion("CNV-1892")
def test_successful_clone_of_large_image(storage_ns):
    with utils.create_dv(
        source="http",
        dv_name="dv-source",
        namespace=storage_ns.name,
        url=f"{get_images_external_http_server()}{WIN_IMAGES_DIR}/{WIN10_QCOW2}",
        size="35Gi",
        storage_class=py_config["default_storage_class"],
    ) as dv:
        dv.wait(timeout=300)
        with utils.create_dv(
            source="pvc",
            dv_name="dv-target",
            namespace=storage_ns.name,
            size="35Gi",
            storage_class=py_config["default_storage_class"],
        ) as cdv:
            cdv.wait(timeout=1500)
            pvc = cdv.pvc
            assert pvc.bound()


@pytest.mark.polarion("CNV-2148")
def test_successful_vm_restart_with_cloned_dv(storage_ns):
    with utils.create_dv(
        source="http",
        dv_name="dv-source",
        namespace=storage_ns.name,
        url=f"{get_images_external_http_server()}{CDI_IMAGES_DIR}/{QCOW2_IMG}",
        size="10Gi",
        storage_class=py_config["default_storage_class"],
    ) as dv:
        dv.wait(timeout=300)
        with utils.create_dv(
            source="pvc",
            dv_name="dv-target",
            namespace=storage_ns.name,
            size="10Gi",
            storage_class=py_config["default_storage_class"],
        ) as cdv:
            cdv.wait(timeout=600)
            with utils.create_vm_from_dv(dv=cdv) as vm_dv:
                utils.check_disk_count_in_vm(vm=vm_dv)
                vm_dv.restart(timeout=300, wait=True)
