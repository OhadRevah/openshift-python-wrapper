"""
Create non-evictable VM with RWO Storage and evictionStrategy=True that should fire the VMCannotBeEvicted alert
"""

import pytest
from ocp_resources.template import Template

from tests.os_params import FEDORA_LATEST, FEDORA_LATEST_LABELS, FEDORA_LATEST_OS
from utilities.constants import HOSTPATH_CSI_BASIC
from utilities.virt import VirtualMachineForTestsFromTemplate, running_vm


@pytest.fixture()
def non_evictable_vm(
    unprivileged_client,
    namespace,
    golden_image_data_source_scope_function,
):
    with VirtualMachineForTestsFromTemplate(
        name="non-evictable-vm",
        namespace=namespace.name,
        client=unprivileged_client,
        labels=Template.generate_template_labels(**FEDORA_LATEST_LABELS),
        data_source=golden_image_data_source_scope_function,
        eviction=True,
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)
        yield vm


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_function",
    [
        pytest.param(
            {
                "dv_name": FEDORA_LATEST_OS,
                "image": FEDORA_LATEST["image_path"],
                "storage_class": HOSTPATH_CSI_BASIC,
                "dv_size": FEDORA_LATEST["dv_size"],
            },
            marks=pytest.mark.polarion("CNV-7484"),
        ),
    ],
    indirect=True,
)
def test_non_evictable_vm_fired_alert(
    prometheus,
    golden_image_data_volume_scope_function,
    non_evictable_vm,
):
    prometheus.alert_sampler(alert="VMCannotBeEvicted")
