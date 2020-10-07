# -*- coding: utf-8 -*-

"""
Common templates RHEL VM migration and SSH access after migration
"""

import pytest
import utilities.virt
from pytest_testconfig import config as py_config
from tests.compute.ssp.supported_os.common_templates import utils
from utilities import console
from utilities.virt import check_ssh_connection, wait_for_console


@pytest.mark.smoke
@pytest.mark.ocp_interop
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function, vm_instance_from_template_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-rhel-migrate-vm",
                "image": py_config["latest_rhel_version"]["image_path"],
                "dv_size": py_config["latest_rhel_version"]["dv_size"],
            },
            {
                "vm_name": "rhel-migrate-vm",
                "start_vm": True,
                "template_labels": py_config["latest_rhel_version"]["template_labels"],
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
    data_volume_multi_storage_scope_function,
    vm_instance_from_template_multi_storage_scope_function,
    vm_ssh_service_multi_storage_scope_function,
    schedulable_node_ips,
):
    """Test CNV common templates with RHEL

    Verify VM is migrated and previously-created expose service (SSH)
    can be accessed.
    """

    wait_for_console(
        vm=vm_instance_from_template_multi_storage_scope_function,
        console_impl=console.RHEL,
    )

    utilities.virt.enable_ssh_service_in_vm(
        vm=vm_instance_from_template_multi_storage_scope_function,
        console_impl=console.RHEL,
    )

    assert check_ssh_connection(
        ip=list(schedulable_node_ips.values())[0],
        port=vm_instance_from_template_multi_storage_scope_function.ssh_node_port,
        console_impl=console.RHEL,
    ), "Failed to login via SSH"

    utils.migrate_vm(vm=vm_instance_from_template_multi_storage_scope_function)

    wait_for_console(
        vm=vm_instance_from_template_multi_storage_scope_function,
        console_impl=console.RHEL,
    )

    # Verify successful SSH connection after migration
    assert check_ssh_connection(
        ip=list(schedulable_node_ips.values())[0],
        port=vm_instance_from_template_multi_storage_scope_function.ssh_node_port,
        console_impl=console.RHEL,
    ), "Failed to login via SSH after migration"
