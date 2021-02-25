"""
CDI Import
"""

import logging

import pytest
from resources.pod import Pod
from resources.storage_class import StorageClass
from resources.utils import TimeoutExpiredError, TimeoutSampler

from utilities.network import LINUX_BRIDGE, network_device, network_nad


LOGGER = logging.getLogger(__name__)
BRIDGE_NAME = "br1-dv"


@pytest.fixture()
def skip_non_shared_storage(storage_class_matrix__function__):
    if [*storage_class_matrix__function__][0] == StorageClass.Types.HOSTPATH:
        pytest.skip(msg="Skipping when storage is non-shared")


def wait_for_importer_container_message(importer_pod, msg):
    LOGGER.info(f"Wait for {importer_pod.name} container to show message: {msg}")
    try:
        sampled_msg = TimeoutSampler(
            wait_timeout=120,
            sleep=5,
            func=lambda: importer_container_status_reason(importer_pod)
            == Pod.Status.CRASH_LOOPBACK_OFF
            and msg
            in importer_pod.instance.status.containerStatuses[0]
            .get("lastState", {})
            .get("terminated", {})
            .get("message", ""),
        )
        for sample in sampled_msg:
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"{importer_pod.name} did not get message: {msg}")
        raise


def importer_container_status_reason(pod):
    """
    Get status for why importer pod container is waiting or terminated
    (for container status running there is no 'reason' key)
    """
    container_state = pod.instance.status.containerStatuses[0].state
    if container_state.waiting:
        return container_state.waiting.reason
    if container_state.terminated:
        return container_state.terminated.reason


@pytest.fixture()
def bridge_on_node(utility_pods, worker_node1):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=BRIDGE_NAME,
        interface_name=BRIDGE_NAME,
        network_utility_pods=utility_pods,
        node_selector=worker_node1.name,
    ) as br:
        yield br


@pytest.fixture()
def linux_nad(namespace, bridge_on_node):
    with network_nad(
        namespace=namespace,
        nad_type=LINUX_BRIDGE,
        nad_name=f"{BRIDGE_NAME}-nad",
        interface_name=bridge_on_node.bridge_name,
    ) as nad:
        yield nad
