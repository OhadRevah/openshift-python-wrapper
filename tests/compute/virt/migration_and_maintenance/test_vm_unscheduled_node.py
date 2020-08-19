# -*- coding: utf-8 -*-

import pytest
from pytest_testconfig import config as py_config
from resources.node_maintenance import NodeMaintenance
from resources.virtual_machine import VirtualMachineInstance
from tests.compute.virt import utils as virt_utils
from tests.conftest import vm_instance_from_template


@pytest.fixture()
def unscheduled_node_vm(
    request,
    worker_node1,
    unprivileged_client,
    namespace,
    data_volume_scope_function,
    network_configuration,
    cloud_init_data,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume=data_volume_scope_function,
        network_configuration=network_configuration,
        cloud_init_data=cloud_init_data,
        node_selector=worker_node1.name,
    ) as vm:
        yield vm


@pytest.mark.parametrize(
    "data_volume_scope_function, unscheduled_node_vm",
    [
        pytest.param(
            {
                "dv_name": "dv-rhel-node-maintenance",
                "image": py_config["latest_rhel_version"]["image_path"],
                "storage_class": py_config["default_storage_class"],
            },
            {
                "vm_name": "rhel-node-maintenance",
                "template_labels": py_config["latest_rhel_version"]["template_labels"],
                "start_vm": False,
            },
        )
    ],
    indirect=True,
)
@pytest.mark.polarion("CNV-4157")
def test_node_maintenance_job_rhel(
    skip_when_one_node,
    nodes,
    data_volume_scope_function,
    unscheduled_node_vm,
    default_client,
):
    """ Test VM scheduling on a node under maintenance.
    1. Start node maintenance job
    2. Once node status is 'Ready,SchedulingDisabled', start a VM (on the
    selected node) and check that VMI phase is 'scheduling'
    3. Wait for node maintenance job to end
    4. Verify the VMI phase is still 'scheduling'
    5. Wait for node status to be 'Ready'
    6. Wait for VMI status to be 'Running'
    7. Verify VMI is running on the selected node
    """
    vm_node = [
        node for node in nodes if node.name == unscheduled_node_vm.node_selector
    ][0]
    with NodeMaintenance(name="node-maintenance-job", node=vm_node) as nm:
        virt_utils.wait_for_node_schedulable_status(node=vm_node, status=False)
        unscheduled_node_vm.start()
        nm.wait_for_status(status=nm.Status.RUNNING)
        unscheduled_node_vm.vmi.wait_for_status(
            status=VirtualMachineInstance.Status.SCHEDULING, timeout=20
        )
        nm.wait_for_status(status=nm.Status.SUCCEEDED)
    assert (
        unscheduled_node_vm.vmi.status == VirtualMachineInstance.Status.SCHEDULING
    ), f"VMI phase should be 'Scheduling', it status is: '{unscheduled_node_vm.vmi.status}"
    virt_utils.wait_for_node_schedulable_status(node=vm_node, status=True)
    unscheduled_node_vm.vmi.wait_for_status(
        status=VirtualMachineInstance.Status.RUNNING
    )
    vmi_node_name = unscheduled_node_vm.vmi.virt_launcher_pod.node.name
    assert (
        vmi_node_name == vm_node.name
    ), f"VMI is running on {vmi_node_name} and not on the selected node {unscheduled_node_vm.node_selector}"
