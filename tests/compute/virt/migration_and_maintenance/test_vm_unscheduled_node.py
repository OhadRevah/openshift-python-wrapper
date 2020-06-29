# -*- coding: utf-8 -*-

import pytest
from pytest_testconfig import config as py_config
from resources.node_maintenance import NodeMaintenance
from resources.virtual_machine import VirtualMachineInstance
from tests.compute.virt import utils as virt_utils
from tests.conftest import vm_instance_from_template


@pytest.fixture()
def vm(
    request,
    schedulable_nodes,
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
        schedulable_nodes=schedulable_nodes,
    ) as vm:
        yield vm


@pytest.mark.parametrize(
    "data_volume_scope_function, vm",
    [
        pytest.param(
            {
                "dv_name": "dv-rhel-node-maintenance",
                "image": py_config["latest_rhel_version"]["image"],
                "storage_class": py_config["default_storage_class"],
            },
            {
                "vm_name": "rhel-node-maintenance",
                "template_labels": {
                    "os": py_config["latest_rhel_version"]["os_label"],
                    "workload": "server",
                    "flavor": "tiny",
                },
                "node_selector_index": 0,
                "start_vm": False,
            },
        )
    ],
    indirect=True,
)
@pytest.mark.polarion("CNV-4157")
def test_node_maintenance_job_rhel(
    skip_when_one_node, nodes, data_volume_scope_function, vm, default_client,
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
    vm_node = [node for node in nodes if node.name == vm.node_selector][0]
    with NodeMaintenance(name="node-maintenance-job", node=vm_node) as nm:
        virt_utils.wait_for_node_schedulable_status(node=vm_node, status=False)
        vm.start()
        nm.wait_for_status(status=nm.Status.RUNNING)
        vm.vmi.wait_for_status(
            status=VirtualMachineInstance.Status.SCHEDULING, timeout=20
        )
        nm.wait_for_status(status=nm.Status.SUCCEEDED)
    assert (
        vm.vmi.status == VirtualMachineInstance.Status.SCHEDULING
    ), f"VMI phase should be 'Scheduling', it status is: '{vm.vmi.status}"
    virt_utils.wait_for_node_schedulable_status(node=vm_node, status=True)
    vm.vmi.wait_for_status(status=VirtualMachineInstance.Status.RUNNING)
    vmi_node_name = vm.vmi.virt_launcher_pod.node.name
    assert (
        vmi_node_name == vm_node.name
    ), f"VMI is running on {vmi_node_name} and not on the selected node {vm.node_selector}"
