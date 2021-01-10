# -*- coding: utf-8 -*-

"""
Common templates RHEL VM migration and SSH access after migration
"""

import pytest
from pytest_testconfig import config as py_config

from tests.compute.utils import migrate_vm
from utilities import console
from utilities.virt import enable_ssh_service_in_vm, wait_for_console


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
                "start_vm": True,
                "template_labels": py_config["latest_rhel_version"]["template_labels"],
                "set_vm_common_cpu": True,
                "username": console.RHEL.USERNAME,
                "password": console.RHEL.PASSWORD,
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
    golden_image_vm_ssh_service_multi_storage_scope_function,
    schedulable_node_ips,
):
    """Test CNV common templates with RHEL

    Verify VM is migrated and previously-created expose service (SSH)
    can be accessed.
    """

    wait_for_console(
        vm=golden_image_vm_instance_from_template_multi_storage_scope_function,
        console_impl=console.RHEL,
    )

    enable_ssh_service_in_vm(
        vm=golden_image_vm_instance_from_template_multi_storage_scope_function,
        console_impl=console.RHEL,
    )

    assert golden_image_vm_instance_from_template_multi_storage_scope_function.ssh_exec.is_connective(
        tcp_timeout=120
    ), "Failed to login via SSH"

    migrate_vm(vm=golden_image_vm_instance_from_template_multi_storage_scope_function)

    wait_for_console(
        vm=golden_image_vm_instance_from_template_multi_storage_scope_function,
        console_impl=console.RHEL,
    )

    # Verify successful SSH connection after migration
    assert golden_image_vm_instance_from_template_multi_storage_scope_function.ssh_exec.is_connective(
        tcp_timeout=120
    ), "Failed to login via SSH after migration"
