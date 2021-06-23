import logging
import time

import pytest
from ocp_resources.resource import ResourceEditor
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler

from tests.metrics.utils import (
    MIN_NUM_VM,
    create_vms,
    enable_swap_fedora_vm,
    get_mutation_component_value_from_prometheus,
    run_node_command,
    run_vm_commands,
)
from utilities.constants import TIMEOUT_10MIN
from utilities.infra import create_ns
from utilities.virt import running_vm


LOGGER = logging.getLogger(__name__)


def wait_for_component_value_to_be_expected(prometheus, component_name, expected_count):
    """This function will wait till the expected value is greater than or equal to
    the value from Prometheus for the specific component_name.

    Args:
        prometheus (:obj:`Prometheus`): Prometheus object.
        component_name (String): Name of the component.
        expected_count (Integer): Expected value of the component after update.

    Returns:
        Integer: It will return the value of the component once it matches to the expected_count.
    """
    current_value = []
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=50,
        func=get_mutation_component_value_from_prometheus,
        prometheus=prometheus,
        component_name=component_name,
    )
    try:
        for sample in samples:
            if sample >= expected_count:
                current_value.append(sample)
                return sample
    except TimeoutExpiredError:
        LOGGER.error(
            f"{component_name} value did not update. Current value {current_value} and expected value {expected_count}"
        )
        raise


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
                    "namespace": hco_namespace.name,
                },
            }
        }
    ):
        yield


@pytest.fixture()
def updated_resource_multiple_times_with_invalid_label(
    request, prometheus, admin_client, hco_namespace
):
    """
    This fixture will repeatedly modify the given resource with invalid metadata labels.


    Args:
        admin_client (DynamicClient): OCP client with Admin permissions
        hco_namespace (Namespace): HCO namespace

    Returns:
        Object: Class ResourceEditor Object.
    """
    res = request.param["resource"]
    count = request.param["count"]
    comp_name = request.param["comp_name"]

    # Resource object
    resource = list(
        res.get(
            dyn_client=admin_client,
            name=request.param.get("name"),
            namespace=hco_namespace.name,
        )
    )[0]

    # Create the ResourceEditor once and then re-use it to make sure we are modifying
    # the resource exactly X times. Restoring it with backup only during teardown.
    resource_editor = ResourceEditor(
        patches={
            resource: {
                "metadata": {
                    "labels": {"test_label": "testing_invalid_label"},
                    "namespace": hco_namespace.name,
                },
            }
        }
    )

    increasing_value = get_mutation_component_value_from_prometheus(
        prometheus=prometheus, component_name=comp_name
    )
    for _ in range(count):
        increasing_value += 1
        resource_editor.update(backup_resources=True)
        wait_for_component_value_to_be_expected(
            prometheus=prometheus,
            component_name=comp_name,
            expected_count=increasing_value,
        )

    yield resource_editor
    resource_editor.restore()


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
        enable_swap_fedora_vm(vm=vm)
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


@pytest.fixture()
def node_setup(request, vm_list, workers_ssh_executors):
    """
    This fixture runs commands on nodes hosting vms and reverses the changes at the end.

    Args:
        vm_list (list): Gets the list of vms created as a part of suite level set up
        workers_ssh_executors (dict): Used to execute commands against nodes (where created vms are scheduled)

    """
    node_command = request.param.get("node_command")

    if node_command:
        vms = vm_list[: request.param.get("num_vms", MIN_NUM_VM)]
        run_node_command(
            vms=vms,
            workers_ssh_executors=workers_ssh_executors,
            command=node_command["setup"],
        )

    yield
    if node_command:
        run_node_command(
            vms=vms,
            workers_ssh_executors=workers_ssh_executors,
            command=node_command["cleanup"],
        )


@pytest.fixture()
def vm_metrics_setup(request, vm_list):
    """
    This fixture runs commands against the vms to generate metrics

    Args:
        vm_list (list): Gets the list of vms created as a part of suite level set up

    Yields:
        list: list of vm objects against which commands to generate metric has been issued
    """
    vm_commands = request.param.get("vm_commands")
    vms = vm_list[: request.param.get("num_vms", MIN_NUM_VM)]
    if vm_commands:
        run_vm_commands(vms=vms, commands=vm_commands)
    yield vms
