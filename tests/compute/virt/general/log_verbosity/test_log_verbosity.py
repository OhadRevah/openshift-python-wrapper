"""
Low level hypervisoer logs testing
"""
import logging

import pytest
from ocp_resources.pod import Pod

from utilities.constants import VIRT_API, VIRT_CONTROLLER, VIRT_HANDLER
from utilities.hco import ResourceEditorValidateHCOReconcile, wait_for_hco_conditions
from utilities.infra import get_pods


LOGGER = logging.getLogger(__name__)
VIRT_LOG_LEVEL = 6


def update_log_verbosity(
    admin_client, hco_namespace, log_verbosity_config, hyperconverged_resource
):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource: {
                "spec": {"logVerbosityConfig": log_verbosity_config}
            }
        },
    ):
        wait_for_hco_conditions(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )
        yield


def assert_log_verbosity_level_in_virt_pods(virt_pods_list):
    failed_log_verbosity = [
        pod.name
        for pod in virt_pods_list
        if f"verbosity to {VIRT_LOG_LEVEL}" not in pod.log()
    ]

    assert (
        not failed_log_verbosity
    ), f"Not found correct verbosity setting: {failed_log_verbosity}"


@pytest.fixture()
def updated_component_log_verbosity_in_hco_cr(
    admin_client, hco_namespace, hyperconverged_resource_scope_function
):
    yield from update_log_verbosity(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        log_verbosity_config={
            "kubevirt": {
                "virtHandler": VIRT_LOG_LEVEL,
                "virtController": VIRT_LOG_LEVEL,
                "virtAPI": VIRT_LOG_LEVEL,
            }
        },
        hyperconverged_resource=hyperconverged_resource_scope_function,
    )


@pytest.fixture()
def updated_node_log_verbosity_in_hco_cr(
    admin_client, hco_namespace, hyperconverged_resource_scope_function, worker_node1
):
    yield from update_log_verbosity(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        log_verbosity_config={
            "kubevirt": {"nodeVerbosity": {worker_node1.name: VIRT_LOG_LEVEL}}
        },
        hyperconverged_resource=hyperconverged_resource_scope_function,
    )


@pytest.fixture()
def virt_component_pods(admin_client, hco_namespace):
    virt_pods_list = []
    for virt_component in [VIRT_HANDLER, VIRT_API, VIRT_CONTROLLER]:
        virt_pods_list.extend(
            get_pods(
                dyn_client=admin_client,
                namespace=hco_namespace,
                label=f"{Pod.ApiGroup.KUBEVIRT_IO}={virt_component}",
            )
        )
    yield virt_pods_list


@pytest.fixture()
def virt_component_pods_in_first_node(worker_node1, virt_component_pods):
    return [pod for pod in virt_component_pods if pod.node.name == worker_node1.name]


@pytest.mark.polarion("CNV-8574")
def test_component_log_verbosity(
    updated_component_log_verbosity_in_hco_cr, virt_component_pods
):
    assert_log_verbosity_level_in_virt_pods(
        virt_pods_list=virt_component_pods,
    )


@pytest.mark.polarion("CNV-8576")
def test_node_component_log_verbosity(
    updated_node_log_verbosity_in_hco_cr, virt_component_pods_in_first_node
):
    assert_log_verbosity_level_in_virt_pods(
        virt_pods_list=virt_component_pods_in_first_node,
    )
