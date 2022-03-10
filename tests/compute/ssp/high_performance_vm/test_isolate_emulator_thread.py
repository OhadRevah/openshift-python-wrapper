"""
Test isolateEmulatorThread feature.
"""
import logging

import pytest
from ocp_resources.template import Template
from pytest_testconfig import config as py_config

from tests.compute.ssp.high_performance_vm.utils import (
    validate_dedicated_emulatorthread,
)
from tests.os_params import RHEL_LATEST, RHEL_LATEST_OS
from utilities.virt import vm_instance_from_template


LOGGER = logging.getLogger(__name__)

VM_DICT = {
    "vm_name": RHEL_LATEST_OS,
    "cpu_placement": True,
    "isolate_emulator_thread": True,
}

TEMPLATE_LABELS = {
    "os": RHEL_LATEST_OS,
    "workload": Template.Workload.SERVER,
}


@pytest.fixture()
def isolated_emulatorthread_vm(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_source_scope_class,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source=golden_image_data_source_scope_class,
    ) as isolated_emulatorthread_vm:
        yield isolated_emulatorthread_vm


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class,",
    [
        pytest.param(
            {
                "dv_name": RHEL_LATEST_OS,
                "image": RHEL_LATEST["image_path"],
                "storage_class": py_config["default_storage_class"],
                "dv_size": RHEL_LATEST["dv_size"],
            },
        ),
    ],
    indirect=True,
)
class TestIsolateEmulatorThread:
    """
    Test Isolated Emulator Thread is used for QEMU Emulator.
    """

    @pytest.mark.parametrize(
        "isolated_emulatorthread_vm,",
        [
            pytest.param(
                {
                    **VM_DICT,
                    "template_labels": {
                        **TEMPLATE_LABELS,
                        "flavor": Template.Flavor.SMALL,
                    },
                },
                marks=pytest.mark.polarion("CNV-6744"),
                id="test_latest_rhel_template_flavor_small",
            ),
            pytest.param(
                {
                    **VM_DICT,
                    "template_labels": {
                        **TEMPLATE_LABELS,
                        "flavor": Template.Flavor.LARGE,
                    },
                },
                marks=pytest.mark.polarion("CNV-6745"),
                id="test_latest_rhel_template_flavor_large",
            ),
        ],
        indirect=True,
    )
    def test_isolate_emulator_thread(
        self,
        isolated_emulatorthread_vm,
    ):
        """
        Test if a dedicated cpu is allocated for QEMU Emulator,
        when isolateEmulatorThread is True.
        """
        # With the Template Flavors being used,
        # As per Flavor ( threads(1) * cores(2) * socket(1))
        # Dedicated cpu will be consumed for CPU Operations.
        # One additional Dedicated cpu is allocated for QEMU Emulator.
        # nproc should still show the CPU count as 2 ( threads(1) * cores(2) * socket(1))
        # even though the VM is allocated overall 3 dedicated cpus.
        validate_dedicated_emulatorthread(vm=isolated_emulatorthread_vm)
