# -*- coding: utf-8 -*-

"""
Windows test suite
"""


import pytest
from tests.compute.ssp.supported_os.common_templates import (
    utils as common_templates_utils,
)
from utilities.infra import Images


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function, vm_instance_from_template_scope_function, started_windows_vm",
    [
        pytest.param(
            {
                "dv_name": "dv-win-19",
                "source": "http",
                "image": f"{Images.Windows.DIR}/{Images.Windows.WIN19_IMG}",
            },
            {
                "vm_name": "win-19",
                "template_labels": {
                    "os": "win2k19",
                    "workload": "server",
                    "flavor": "medium",
                },
                "cpu_threads": 2,
            },
            {"os_version": "19"},
            marks=pytest.mark.polarion("CNV-3637"),
        ),
    ],
    indirect=True,
)
def test_successful_dv_creation_large_image(
    skip_upstream,
    unprivileged_client,
    namespace,
    data_volume_multi_storage_scope_function,
    vm_instance_from_template_scope_function,
    winrmcli_pod_scope_function,
    bridge_attached_helper_vm,
    started_windows_vm,
):
    common_templates_utils.validate_windows_guest_agent_info(
        vm=vm_instance_from_template_scope_function,
        winrmcli_pod=winrmcli_pod_scope_function,
        helper_vm=bridge_attached_helper_vm,
    )
