import pytest

from tests.install_upgrade_operators.pod_validation.utils import (
    validate_cnv_pod_cpu_min_value,
    validate_cnv_pods_priority_class_name_exists,
    validate_cnv_pods_resource_request,
    validate_priority_class_value,
)


@pytest.mark.polarion("CNV-7261")
def test_pods_priority_class_name(cnv_pods):
    validate_cnv_pods_priority_class_name_exists(cnv_pods=cnv_pods)


@pytest.mark.polarion("CNV-7262")
def test_pods_priority_class_value(cnv_pods):
    validate_priority_class_value(cnv_pods=cnv_pods)


@pytest.mark.parametrize(
    "request_field",
    [
        pytest.param(
            "cpu",
            marks=(pytest.mark.polarion("CNV-7306")),
            id="test_pods_resource_request_cpu",
        ),
        pytest.param(
            "memory",
            marks=(pytest.mark.polarion("CNV-7307")),
            id="test_pods_resource_request_memory",
        ),
    ],
)
def test_pods_resource_request_cpu(cnv_pods, request_field):
    validate_cnv_pods_resource_request(cnv_pods=cnv_pods, request_field=request_field)


@pytest.mark.parametrize(
    "cpu_min_value",
    [
        pytest.param(
            5,
            marks=(pytest.mark.polarion("CNV-7341")),
            id="test_pods_resource_request_cpu",
        ),
    ],
)
def test_pods_resource_request_cpu_value(cnv_pods, cpu_min_value):
    """Test validates that resources.requests.cpu value for all cnv pods meet minimum threshold requirement"""
    cpu_error = {}
    for pod in cnv_pods:
        invalid_cpu = validate_cnv_pod_cpu_min_value(
            cnv_pod=pod, cpu_min_value=cpu_min_value
        )
        if invalid_cpu:
            cpu_error[pod.name] = invalid_cpu
    assert not cpu_error, f"For following pods invalid cpu values found: {cpu_error}"
