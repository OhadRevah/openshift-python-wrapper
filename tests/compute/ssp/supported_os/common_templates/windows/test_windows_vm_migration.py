# -*- coding: utf-8 -*-

"""
Common templates Windows VM migration and SSH access after migration
"""

import pytest
from pytest_testconfig import config as py_config

import utilities.virt
from tests.compute.ssp.supported_os.common_templates import utils
from tests.compute.utils import migrate_vm


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function, vm_instance_from_template_multi_storage_scope_function, "
    "started_windows_vm, exposed_vm_service_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-windows-migrate-vm",
                "image": py_config["latest_windows_version"]["image_path"],
                "dv_size": py_config["latest_windows_version"]["dv_size"],
            },
            {
                "vm_name": "windows-migrate-vm",
                "start_vm": True,
                "guest_agent": False,
                "template_labels": py_config["latest_windows_version"][
                    "template_labels"
                ],
                "cpu_threads": 2,
                "set_vm_common_cpu": True,
                "ssh": True,
                "username": py_config["windows_username"],
                "password": py_config["windows_password"],
            },
            {"os_version": py_config["latest_windows_version"]["os_version"]},
            {"service_name": "telnet", "service_port": 5985},
            marks=pytest.mark.polarion("CNV-3335"),
        ),
    ],
    indirect=True,
)
def test_migrate_vm_windows(
    skip_rhel7_workers,
    skip_upstream,
    skip_access_mode_rwo_scope_function,
    namespace,
    data_volume_multi_storage_scope_function,
    vm_instance_from_template_multi_storage_scope_function,
    started_windows_vm,
    exposed_vm_service_multi_storage_scope_function,
):
    """Test CNV common templates with Windows

    Verify VM is migrated and previously-created expose service (winrm)
    can be accessed.
    """

    assert utils.check_telnet_connection(
        ip=vm_instance_from_template_multi_storage_scope_function.custom_service.service_ip,
        port=vm_instance_from_template_multi_storage_scope_function.custom_service.service_port,
    ), "Failed to login via Telnet"

    migrate_vm(vm=vm_instance_from_template_multi_storage_scope_function)

    utilities.virt.wait_for_windows_vm(
        vm=vm_instance_from_template_multi_storage_scope_function,
        version=py_config["latest_windows_version"]["os_version"],
        timeout=1800,
    )

    assert utils.check_telnet_connection(
        ip=vm_instance_from_template_multi_storage_scope_function.custom_service.service_ip,
        port=vm_instance_from_template_multi_storage_scope_function.custom_service.service_port,
    ), "Failed to login via Telnet after migration"
