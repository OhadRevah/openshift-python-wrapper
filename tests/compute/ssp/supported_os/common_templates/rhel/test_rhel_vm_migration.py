# -*- coding: utf-8 -*-

"""
Common templates RHEL VM migration and SSH access after migration
"""

import pytest
from pytest_testconfig import config as py_config
from resources.datavolume import DataVolume
from tests.compute.ssp.supported_os.common_templates import utils
from utilities import console


@pytest.mark.parametrize(
    "data_volume_scope_function, vm_instance_from_template_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-rhel-migrate-vm",
                "image": py_config.get("latest_rhel_version", {}).get("image"),
                "access_modes": DataVolume.AccessMode.RWX,
                "volume_mode": DataVolume.VolumeMode.BLOCK,
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
def test_migrate_vm_rhel(
    skip_rhel7_workers,
    skip_upstream,
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

    utils.enable_ssh_service_in_vm(
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
