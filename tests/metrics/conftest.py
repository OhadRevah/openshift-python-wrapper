import logging
import time

import pytest
from ocp_resources.resource import ResourceEditor

from tests.metrics.utils import create_vms, get_mutation_component_value_from_prometheus
from utilities.infra import create_ns
from utilities.virt import running_vm


LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def updated_resource_with_invalid_label(request, admin_client, hco_namespace):
    res = request.param["resource"]
    resource = list(
        res.get(
            dyn_client=admin_client,
            name=request.param.get("name"),
            namespace=hco_namespace.name,
        )
    )[0]

    with ResourceEditor(
        patches={
            resource: {
                "metadata": {
                    "labels": {"test_label": "testing_invalid_label"},
                },
                "namespace": hco_namespace.name,
            }
        }
    ):
        yield


@pytest.fixture()
def mutation_count_before_change(request, prometheus):
    component_name = request.param
    LOGGER.info(f"Getting component '{component_name}' mutation count before change.")
    return get_mutation_component_value_from_prometheus(
        prometheus=prometheus,
        component_name=component_name,
    )


@pytest.fixture(scope="class")
def unique_namespace(unprivileged_client):
    """
    Creates a namespace to be used by key metrics test cases.

    Yields:
        Namespace object to be used by the tests
    """
    namespace_name = f"key-metrics-{time.time()}".replace(".", "-")
    yield from create_ns(unprivileged_client=unprivileged_client, name=namespace_name)


@pytest.fixture(scope="class")
def vm_list(unique_namespace):
    """
    Creates n vms, waits for them all to go to running state and cleans them up at the end

    Args:
        unique_namespace (Namespace): Creates namespaces to be used by the test

    Yields:
        list: list of VirtualMachineForTests created
    """
    vms_list = create_vms(
        name_prefix="key-metric-vm", namespace_name=unique_namespace.name
    )
    for vm in vms_list:
        running_vm(vm=vm)
    yield vms_list
    for vm in vms_list:
        vm.clean_up()


@pytest.fixture()
def first_metric_vm(vm_list):
    """
    Returns the first vm from the list of created vms

    Args:
        vm_list (list): list of VirtualMachineForTests created

    Returns:
        VirtualMachineForTests: a VirtualMachineForTests object
    """
    return vm_list[0]
