# -*- coding: utf-8 -*-

"""
Common templates RHEL VM migration and SSH access after migration
"""

import pytest
import utilities.virt
from pytest_testconfig import config as py_config
from tests.compute.ssp.supported_os.common_templates import utils
from utilities import console
from utilities.infra import BUG_STATUS_CLOSED


@pytest.mark.parametrize(
    "data_volume_scope_function, vm_instance_from_template_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-rhel-migrate-vm",
                "image": py_config.get("latest_rhel_version", {}).get("image"),
            },
            {
                "vm_name": "rhel-migrate-vm",
                "start_vm": True,
                "template_labels": {
                    "os": py_config.get("latest_rhel_version", {}).get("os_label"),
                    "workload": "server",
                    "flavor": "tiny",
                },
            },
            marks=pytest.mark.polarion("CNV-3038"),
        ),
    ],
    indirect=True,
)
@pytest.mark.bugzilla(
    1810493, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)
def test_migrate_vm_rhel(
    skip_rhel7_workers,
    skip_upstream,
    skip_migration_access_mode_rwo,
    namespace,
    data_volume_scope_function,
    vm_instance_from_template_scope_function,
    vm_ssh_service_scope_function,
    schedulable_node_ips,
):
    """ Test CNV common templates with RHEL

    Verify VM is migrated and previously-created expose service (SSH)
    can be accessed.
    """

    utils.wait_for_console(vm_instance_from_template_scope_function, console.RHEL)

    utilities.virt.enable_ssh_service_in_vm(
        vm=vm_instance_from_template_scope_function, console_impl=console.RHEL
    )

    assert utils.check_ssh_connection(
        ip=list(schedulable_node_ips.values())[0],
        port=vm_instance_from_template_scope_function.ssh_node_port,
        console_impl=console.RHEL,
    ), "Failed to login via SSH"

    utils.migrate_vm(vm_instance_from_template_scope_function)

    utils.wait_for_console(vm_instance_from_template_scope_function, console.RHEL)

    # Verify successful SSH connection after migration
    assert utils.check_ssh_connection(
        ip=list(schedulable_node_ips.values())[0],
        port=vm_instance_from_template_scope_function.ssh_node_port,
        console_impl=console.RHEL,
    ), "Failed to login via SSH after migration"
