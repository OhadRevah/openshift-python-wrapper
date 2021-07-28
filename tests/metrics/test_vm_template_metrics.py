import re

import pytest
from ocp_resources.storage_class import StorageClass
from pytest_testconfig import py_config

from tests.metrics import utils


QUERY_FORMAT_DICT = {
    "kubevirt_vmi_phase_count": (
        'kubevirt_vmi_phase_count{{os="{os_name}", flavor="{flavor}", workload="{workload}"}}'
    ),
    "sum_kubevirt_vmi_phase_count": (
        'sum (kubevirt_vmi_phase_count{{os="{os_name}", flavor="{flavor}", workload="{workload}"}})'
    ),
}


def get_matrix_name(os_name):
    matrix_os_name = ""
    if "win" in os_name:
        matrix_os_name = re.sub("^win(?!=dows)", "windows", os_name)
    if os_name.startswith(("rhel", "centos")):
        matrix_os_name = os_name.split(".", 1)[0]
    if os_name.startswith("fedora"):
        matrix_os_name = "fedora"
    return f"{matrix_os_name.partition('-')[0]}_os_matrix"


def generate_skipif_params(os_name):
    return {
        "condition": os_name
        not in [
            os_in_matrix
            for item in py_config.get(get_matrix_name(os_name), [])
            for os_in_matrix in item
        ],
        "reason": "current environment does not have the os in its config",
    }


def generate_test_param(os_name, start_vm=True):
    """
    This function creates automatically the params necessary for each test.
    It verifies if each test can be run with the global_config within the environment.
    The reason for adding it was CI failure: CI uses global_config_ci.py which does not have all the os matrices.
    Therefore, tests that cannot run, will be marked with the skipif marker in order to skip them.
    Longer explanation for all attempts which led to this code:
    https://coreos.slack.com/archives/C010TJVV3J4/p1626322631051100

    Args:
        os_name (str): the OS name as it appears in the global_config matrix
        start_vm (bool, default: True): toggle to start the VM upon creation

    Returns:
        list of values matching the test function's parameters (and fixtures)
    """
    os_data_list = [
        template_data
        for entry in py_config.get(get_matrix_name(os_name), [])
        for template_name, template_data in entry.items()
    ]
    os_data_dict = os_data_list[0] if os_data_list else None
    query = QUERY_FORMAT_DICT[
        "sum_kubevirt_vmi_phase_count" if start_vm else "kubevirt_vmi_phase_count"
    ]
    count_increase = int(start_vm)
    if os_data_dict:
        vmi_phase_count_before = {
            "labels": os_data_dict["template_labels"],
            "query": query,
        }
        golden_image_data_volume_scope_function = {
            "dv_name": os_data_dict["template_labels"]["os"],
            "image": os_data_dict["image_path"],
            "dv_size": os_data_dict["dv_size"],
            "storage_class": StorageClass.Types.HOSTPATH,
        }
        vm_from_template = {
            "vm_name": os_name,
            "template_labels": os_data_dict["template_labels"],
            "guest_agent": False,
            "ssh": False,
            "start_vm": start_vm,
        }
    else:
        vmi_phase_count_before = None
        golden_image_data_volume_scope_function = None
        vm_from_template = None

    return [
        query,
        count_increase,
        vmi_phase_count_before,
        golden_image_data_volume_scope_function,
        vm_from_template,
    ]


@pytest.mark.usefixtures("prometheus")
class TestVmTemplateMetrics:
    @pytest.mark.parametrize(
        (
            "query",
            "count_increase",
            "vmi_phase_count_before",
            "golden_image_data_volume_scope_function",
            "vm_from_template",
        ),
        [
            pytest.param(
                *generate_test_param(os_name="centos-7"),
                marks=(
                    pytest.mark.polarion("CNV-6502"),
                    pytest.mark.skipif(**generate_skipif_params("centos-7")),
                ),
                id="test_metric_on_vm_from_template_centos_7",
            ),
            pytest.param(
                *generate_test_param(os_name="centos-7", start_vm=False),
                marks=(
                    pytest.mark.polarion("CNV-6798"),
                    pytest.mark.skipif(**generate_skipif_params("centos-7")),
                ),
                id="test_metric_on_vm_from_template_centos_7_not_running",
            ),
            pytest.param(
                *generate_test_param(os_name="centos-8"),
                marks=(
                    pytest.mark.polarion("CNV-6503"),
                    pytest.mark.skipif(**generate_skipif_params("centos-8")),
                ),
                id="test_metric_on_vm_from_template_centos_8",
            ),
            pytest.param(
                *generate_test_param(os_name="fedora-34"),
                marks=(
                    pytest.mark.polarion("CNV-6504"),
                    pytest.mark.skipif(**generate_skipif_params("fedora-34")),
                ),
                id="test_metric_on_vm_from_template_fedora_34",
            ),
            pytest.param(
                *generate_test_param(os_name="rhel-6-10"),
                marks=(
                    pytest.mark.polarion("CNV-6506"),
                    pytest.mark.skipif(**generate_skipif_params("rhel-6-10")),
                ),
                id="test_metric_on_vm_from_template_rhel_6_10",
            ),
            pytest.param(
                *generate_test_param(os_name="rhel-7-9"),
                marks=(
                    pytest.mark.polarion("CNV-6507"),
                    pytest.mark.skipif(**generate_skipif_params("rhel-7-9")),
                ),
                id="test_metric_on_vm_from_template_rhel_7_9",
            ),
            pytest.param(
                *generate_test_param(os_name="rhel-8-5"),
                marks=(
                    pytest.mark.polarion("CNV-6508"),
                    pytest.mark.skipif(**generate_skipif_params("rhel-8-5")),
                ),
                id="test_metric_on_vm_from_template_rhel_8_5",
            ),
            pytest.param(
                *generate_test_param(os_name="rhel-9-0"),
                marks=(
                    pytest.mark.polarion("CNV-6848"),
                    pytest.mark.skipif(**generate_skipif_params("rhel-9-0")),
                ),
                id="test_metric_on_vm_from_template_rhel_9_0",
            ),
            pytest.param(
                *generate_test_param(os_name="win-10"),
                marks=(
                    pytest.mark.polarion("CNV-6510"),
                    pytest.mark.skipif(**generate_skipif_params("win-10")),
                ),
                id="test_metric_on_vm_from_template_win_10",
            ),
            pytest.param(
                *generate_test_param(os_name="win-12"),
                marks=(
                    pytest.mark.polarion("CNV-6511"),
                    pytest.mark.skipif(**generate_skipif_params("win-12")),
                ),
                id="test_metric_on_vm_from_template_win_12",
            ),
            pytest.param(
                *generate_test_param(os_name="win-16"),
                marks=(
                    pytest.mark.polarion("CNV-6512"),
                    pytest.mark.skipif(**generate_skipif_params("win-16")),
                ),
                id="test_metric_on_vm_from_template_win_16",
            ),
            pytest.param(
                *generate_test_param(os_name="win-19"),
                marks=(
                    pytest.mark.polarion("CNV-6513"),
                    pytest.mark.skipif(**generate_skipif_params("win-19")),
                ),
                id="test_metric_on_vm_from_template_win_19",
            ),
        ],
        indirect=[
            "vmi_phase_count_before",
            "golden_image_data_volume_scope_function",
            "vm_from_template",
        ],
    )
    def test_vmi_phase_count_metric(
        self,
        query,
        count_increase,
        prometheus,
        vmi_phase_count_before,
        golden_image_data_volume_scope_function,
        vm_from_template,
    ):
        """
        Templates have some annotations regarding OS, FLAVOR and WORKLOAD. 'kubevirt_vmi_phase_count' must show
        the number of VMIs with given os, flavor or workload by respecting those annotations.

        Args:
            prometheus (Prometheus): a Prometheus object to which queries for metrics are sent
            vmi_phase_count_before (fixture): metric count fetched by a query before the VM was created
            golden_image_data_volume_scope_function (fixture): data volume of the golden image
            vm_from_template (fixture): a VM object after it was created from a VM template
        """
        vmi_annotations = vm_from_template.instance.spec.template.metadata.annotations
        utils.wait_until_kubevirt_vmi_phase_count_is_expected(
            prometheus=prometheus,
            os_name=vmi_annotations["vm.kubevirt.io/os"],
            flavor=vmi_annotations["vm.kubevirt.io/flavor"],
            workload=vmi_annotations["vm.kubevirt.io/workload"],
            expected=vmi_phase_count_before + count_increase,
            query=query,
        )
