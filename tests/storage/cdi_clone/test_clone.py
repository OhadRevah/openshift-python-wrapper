# -*- coding: utf-8 -*-

"""
Clone tests
"""

import pytest
import utilities.storage
from pytest_testconfig import config as py_config
from tests.storage import utils
from utilities.infra import Images, get_images_external_http_server


@pytest.mark.polarion("CNV-1892")
def test_successful_clone_of_large_image(skip_upstream, storage_ns):
    with utilities.storage.create_dv(
        source="http",
        dv_name="dv-source",
        namespace=storage_ns.name,
        url=f"{get_images_external_http_server()}{Images.Windows.DIR}/{Images.Windows.WIM10_IMG}",
        size="35Gi",
        storage_class=py_config["default_storage_class"],
        volume_mode=py_config["default_volume_mode"],
    ) as dv:
        dv.wait(timeout=300)
        with utilities.storage.create_dv(
            source="pvc",
            dv_name="dv-target",
            namespace=storage_ns.name,
            size="35Gi",
            storage_class=py_config["default_storage_class"],
            volume_mode=py_config["default_volume_mode"],
        ) as cdv:
            cdv.wait(timeout=1500)
            pvc = cdv.pvc
            assert pvc.bound()


@pytest.mark.polarion("CNV-2148")
def test_successful_vm_restart_with_cloned_dv(skip_upstream, storage_ns):
    with utilities.storage.create_dv(
        source="http",
        dv_name="dv-source",
        namespace=storage_ns.name,
        url=f"{get_images_external_http_server()}{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
        size="10Gi",
        storage_class=py_config["default_storage_class"],
        volume_mode=py_config["default_volume_mode"],
    ) as dv:
        dv.wait(timeout=300)
        with utilities.storage.create_dv(
            source="pvc",
            dv_name="dv-target",
            namespace=storage_ns.name,
            size="10Gi",
            storage_class=py_config["default_storage_class"],
            volume_mode=py_config["default_volume_mode"],
        ) as cdv:
            cdv.wait(timeout=600)
            with utils.create_vm_from_dv(dv=cdv) as vm_dv:
                utils.check_disk_count_in_vm(vm=vm_dv)
                vm_dv.restart(timeout=300, wait=True)
