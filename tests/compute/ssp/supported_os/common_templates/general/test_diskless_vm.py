# -*- coding: utf-8 -*-

"""
Test diskless VM creation.
"""

import logging

import pytest
from pytest_testconfig import config as py_config

from tests.conftest import vm_instance_from_template
from utilities.infra import Images


LOGGER = logging.getLogger(__name__)
# Image is not relevant - needed for VM creation with a template but will not be used
SMALL_VM_IMAGE = f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}"


@pytest.fixture()
def diskless_vm(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_volume_scope_function,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume=golden_image_data_volume_scope_function,
    ) as diskless_vm:
        yield diskless_vm


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_function, diskless_vm",
    [
        pytest.param(
            {
                "dv_name": "cirros-dv",
                "image": SMALL_VM_IMAGE,
                "storage_class": py_config["default_storage_class"],
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
            },
            {
                "vm_name": "rhel-diskless-vm",
                "template_labels": py_config["latest_rhel_version"]["template_labels"],
                "diskless_vm": True,
                "start_vm": False,
            },
            marks=pytest.mark.polarion("CNV-4696"),
        ),
        pytest.param(
            {
                "dv_name": "cirros-dv",
                "image": SMALL_VM_IMAGE,
                "storage_class": py_config["default_storage_class"],
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
            },
            {
                "vm_name": "windows-diskless-vm",
                "template_labels": py_config["latest_windows_version"][
                    "template_labels"
                ],
                "diskless_vm": True,
                "start_vm": False,
            },
            marks=(pytest.mark.polarion("CNV-4697"),),
        ),
    ],
    indirect=True,
)
def test_diskless_vm_creation(
    skip_upstream,
    unprivileged_client,
    namespace,
    golden_image_data_volume_scope_function,
    diskless_vm,
):
    LOGGER.info("Verify diskless VM is created.")
    assert diskless_vm.exists, f"{diskless_vm.name} VM was not created."