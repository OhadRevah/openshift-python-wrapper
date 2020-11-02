# -*- coding: utf-8 -*-

"""
Base templates test
"""

import logging

import pytest
from openshift.dynamic.exceptions import UnprocessibleEntityError
from pytest_testconfig import config as py_config
from utilities.infra import Images


LOGGER = logging.getLogger(__name__)
# Negative tests require a DV, however its content is not important (VM will not be created).
FAILED_VM_IMAGE = f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}"


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function, vm_object_from_template_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-rhel-min-memory-validation",
                "image": FAILED_VM_IMAGE,
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
            },
            {
                "vm_name": "rhel-min-memory-validation",
                "template_labels": py_config["latest_rhel_version"]["template_labels"],
                "memory_requests": "0.5G",
            },
            marks=pytest.mark.polarion("CNV-2960"),
        ),
    ],
    indirect=True,
)
def test_template_validation_min_memory(
    data_volume_multi_storage_scope_function,
    vm_object_from_template_multi_storage_scope_function,
):
    LOGGER.info("Test template validator - minimum required memory")

    with pytest.raises(UnprocessibleEntityError) as vm_exception:
        vm_object_from_template_multi_storage_scope_function.create()

        assert (
            "This VM requires more memory" in vm_exception.value.body.decode()
        ), f"VM failure with wrong reason {vm_exception}"
