import pytest
from pytest_testconfig import config as py_config

from tests.install_upgrade_operators.metrics.utils import (
    validate_vm_vcpu_cpu_affinity_with_prometheus,
)
from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS, RHEL_LATEST_OS


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class, vm_from_template",
    [
        pytest.param(
            {
                "dv_name": RHEL_LATEST_OS,
                "image": RHEL_LATEST["image_path"],
                "storage_class": py_config["default_storage_class"],
                "dv_size": RHEL_LATEST["dv_size"],
            },
            {
                "vm_name": "rhel-latest",
                "template_labels": RHEL_LATEST_LABELS,
                "guest_agent": False,
                "ssh": False,
            },
        ),
    ],
    indirect=True,
)
class TestVMICPUAffinity:
    @pytest.mark.polarion("CNV-7295")
    def test_kubevirt_vmi_cpu_affinity(
        self, prometheus, schedulable_nodes, vm_from_template
    ):
        """This test will check affinity of vcpu and cpu from query and VM."""
        validate_vm_vcpu_cpu_affinity_with_prometheus(
            vm=vm_from_template,
            prometheus=prometheus,
            nodes=schedulable_nodes,
            query=f'kubevirt_vmi_cpu_affinity{{kubernetes_vmi_label_kubevirt_io_domain="{vm_from_template.name}"}}',
        )
