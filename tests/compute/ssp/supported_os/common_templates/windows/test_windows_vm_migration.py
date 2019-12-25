# -*- coding: utf-8 -*-

"""
Common templates Windows VM migration and SSH access after migration
"""

import pytest
from pytest_testconfig import config as py_config
from resources.datavolume import DataVolume
from tests.compute.ssp.supported_os.common_templates import utils


@pytest.mark.parametrize(
    "data_volume_scope_function, vm_instance_from_template_scope_function, "
    "started_windows_vm, exposed_vm_service",
    [
        pytest.param(
            {
                "dv_name": "dv-windows-migrate-vm",
                "image": py_config.get("latest_windows_version", {}).get("image"),
                "access_modes": DataVolume.AccessMode.RWX,
                "volume_mode": DataVolume.VolumeMode.BLOCK,
            },
            {
                "vm_name": "windows-migrate-vm",
                "start_vm": True,
                "guest_agent": False,
                "template_labels": {
                    "os": py_config.get("latest_windows_version", {}).get("os_label"),
                    "workload": "server",
                    "flavor": "medium",
                },
                "cpu_threads": 2,
            },
            {
                "os_version": py_config.get("latest_windows_version", {}).get(
                    "os_label"
                )[-2:],
            },
            {"service_name": "telnet", "service_port": 5985},
            marks=pytest.mark.polarion("CNV-3335"),
        ),
    ],
    indirect=True,
)
def test_migrate_vm_windows(
    skip_upstream,
    namespace,
    data_volume_scope_function,
    vm_instance_from_template_scope_function,
    winrmcli_pod_scope_function,
    started_windows_vm,
    exposed_vm_service,
    schedulable_node_ips,
):
    """ Test CNV common templates with Windows

    Verify VM is migrated and previously-created expose service (winrm)
    can be accessed.
    """

    assert utils.check_telnet_connection(
        ip=list(schedulable_node_ips.values())[0],
        port=vm_instance_from_template_scope_function.custom_service_port,
    ), "Failed to login via Telnet"

    utils.migrate_vm(vm_instance_from_template_scope_function)

    utils.wait_for_windows_vm(
        vm=vm_instance_from_template_scope_function,
        version=py_config["latest_windows_version"]["os_label"][-2:],
        winrmcli_pod=winrmcli_pod_scope_function,
        timeout=1800,
    )

    assert utils.check_telnet_connection(
        ip=list(schedulable_node_ips.values())[0],
        port=vm_instance_from_template_scope_function.custom_service_port,
    ), "Failed to login via Telnet after migration"
