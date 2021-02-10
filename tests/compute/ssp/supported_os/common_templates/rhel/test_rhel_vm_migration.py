# -*- coding: utf-8 -*-

"""
Common templates RHEL VM migration and SSH access after migration
"""

import pytest
from pytest_testconfig import config as py_config

from tests.compute.utils import migrate_vm


@pytest.mark.smoke
@pytest.mark.ocp_interop
@pytest.mark.parametrize(
    "golden_image_data_volume_multi_storage_scope_function,"
    "golden_image_vm_instance_from_template_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": py_config["latest_rhel_version"]["template_labels"]["os"],
                "image": py_config["latest_rhel_version"]["image_path"],
                "dv_size": py_config["latest_rhel_version"]["dv_size"],
            },
            {
                "vm_name": "rhel-migrate-vm",
                "template_labels": py_config["latest_rhel_version"]["template_labels"],
                "set_vm_common_cpu": True,
            },
            marks=pytest.mark.polarion("CNV-3038"),
        ),
    ],
    indirect=True,
)
def test_migrate_vm_rhel(
    skip_rhel7_workers,
    skip_upstream,
    skip_access_mode_rwo_scope_function,
    namespace,
    golden_image_data_volume_multi_storage_scope_function,
    golden_image_vm_instance_from_template_multi_storage_scope_function,
):
    """Test CNV common templates with RHEL

    Verify VM is migrated and previously-created expose service (SSH)
    can be accessed.
    """
    migrate_vm(vm=golden_image_vm_instance_from_template_multi_storage_scope_function)

    # Verify successful SSH connection after migration
    assert golden_image_vm_instance_from_template_multi_storage_scope_function.ssh_exec.executor().is_connective(
        tcp_timeout=240
    ), "Failed to login via SSH after migration"
