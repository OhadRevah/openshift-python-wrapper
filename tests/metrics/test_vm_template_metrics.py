import os

import pytest
from pytest_testconfig import config as py_config

from tests.metrics import utils
from tests.os_params import RHEL_LATEST_LABELS, RHEL_LATEST_OS
from utilities.constants import Images


pytestmark = pytest.mark.sno
METRIC_QUERY = 'kubevirt_vmi_phase_count{{os="{os_name}", flavor="{flavor}", workload="{workload}"}}'
SUM_QUERY = f"sum({METRIC_QUERY})"


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class, vmi_phase_count_before, vm_from_template",
    [
        pytest.param(
            {
                "dv_name": RHEL_LATEST_OS,
                # Cirros is used because the underlying OS is not relevant for this test
                "image": os.path.join(Images.Cirros.DIR, Images.Cirros.QCOW2_IMG),
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
                "storage_class": py_config["default_storage_class"],
            },
            {
                "labels": RHEL_LATEST_LABELS,
                "query": SUM_QUERY,
            },
            {
                "vm_name": "fedora-latest",
                "template_labels": RHEL_LATEST_LABELS,
                "guest_agent": False,
                "ssh": False,
            },
        ),
    ],
    indirect=True,
)
class TestVmTemplateMetrics:
    @pytest.mark.polarion("CNV-6504")
    @pytest.mark.dependency(name="test_vmi_phase_count_metric")
    @pytest.mark.order(before="test_vmi_phase_count_metric_after_stopped_vm")
    def test_vmi_phase_count_metric(
        self,
        prometheus,
        vmi_phase_count_before,
        vm_from_template,
    ):
        utils.wait_until_kubevirt_vmi_phase_count_is_expected(
            prometheus=prometheus,
            vmi_annotations=vm_from_template.instance.spec.template.metadata.annotations,
            expected=vmi_phase_count_before + 1,
            query=SUM_QUERY,
        )

    @pytest.mark.polarion("CNV-6798")
    @pytest.mark.dependency(
        depends=["test_vmi_phase_count_metric"],
    )
    def test_vmi_phase_count_metric_after_stopped_vm(
        self,
        prometheus,
        vmi_phase_count_before,
        stopped_vm,
    ):
        utils.wait_until_kubevirt_vmi_phase_count_is_expected(
            prometheus=prometheus,
            vmi_annotations=stopped_vm.instance.spec.template.metadata.annotations,
            expected=vmi_phase_count_before,
            query=METRIC_QUERY,
        )
