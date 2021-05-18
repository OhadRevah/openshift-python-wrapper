import pytest
from ocp_resources.utils import TimeoutSampler
from ocp_resources.virtual_machine import VirtualMachineInstance

from tests.compute.utils import vm_started
from utilities.virt import LOGGER, Prometheus, VirtualMachineForTests, fedora_vm_body


@pytest.fixture(scope="class")
def prometheus():
    return Prometheus()


@pytest.fixture(scope="class")
def vm_metric_1(namespace, unprivileged_client):
    vm_name = "vm-metrics-1"
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace.name,
        body=fedora_vm_body(name=vm_name),
        client=unprivileged_client,
    ) as vm:
        vm_started(vm=vm, wait_for_interfaces=False)
        yield vm


@pytest.fixture(scope="class")
def vm_metric_2(namespace, unprivileged_client):
    vm_name = "vm-metrics-2"
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace.name,
        body=fedora_vm_body(name=vm_name),
        client=unprivileged_client,
    ) as vm:
        vm_started(vm=vm, wait_for_interfaces=False)
        yield vm


@pytest.fixture(scope="class")
def number_of_vmis_exists(admin_client):
    return len(list(VirtualMachineInstance.get(admin_client)))


def check_vmi_metric(prometheus):
    response = prometheus.query(
        query="/api/v1/query?query=cnv:vmi_status_running:count"
    )
    assert response["status"] == "success"
    return sum(int(node["value"][1]) for node in response["data"]["result"])


def check_vmi_count_metric(expected_vmi_count, prometheus):
    LOGGER.info(f"Check VMI metric expected: {expected_vmi_count}")
    samples = TimeoutSampler(
        wait_timeout=100,
        sleep=5,
        func=check_vmi_metric,
        prometheus=prometheus,
    )
    for sample in samples:
        if sample == expected_vmi_count:
            return True


class TestVMICountMetric:
    @pytest.mark.polarion("CNV-3048")
    def test_vmi_count_metric_increase(
        self,
        skip_not_openshift,
        prometheus,
        number_of_vmis_exists,
        vm_metric_1,
        vm_metric_2,
    ):
        assert check_vmi_count_metric(number_of_vmis_exists + 2, prometheus)

    @pytest.mark.polarion("CNV-3589")
    def test_vmi_count_metric_decrease(
        self,
        skip_not_openshift,
        prometheus,
        number_of_vmis_exists,
        vm_metric_1,
        vm_metric_2,
    ):
        vm_metric_2.stop(wait=True)
        assert check_vmi_count_metric(number_of_vmis_exists + 1, prometheus)
