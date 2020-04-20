"""
CDI Import
"""

import logging

import pytest
from resources.configmap import ConfigMap
from resources.persistent_volume_claim import PersistentVolumeClaim
from resources.pod import Pod
from resources.storage_class import StorageClass
from resources.utils import TimeoutExpiredError, TimeoutSampler


LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def https_config_map(request, namespace):
    data = request.param["data"] if request else None
    with ConfigMap(
        name="https-cert", namespace=namespace.name, cert_name="ca.pem", data=data,
    ) as configmap:
        yield configmap


@pytest.fixture()
def skip_access_mode_rwo(storage_class_matrix__class__):
    LOGGER.debug("Use 'skip_access_mode_rwo' fixture...")
    if (
        storage_class_matrix__class__[[*storage_class_matrix__class__][0]][
            "access_mode"
        ]
        == PersistentVolumeClaim.AccessMode.RWO
    ):
        pytest.skip(msg="Skipping when access_mode is RWO")


@pytest.fixture()
def skip_non_shared_storage(storage_class_matrix__class__):
    LOGGER.debug("Use 'skip_non_shared_storage' fixture...")
    if [*storage_class_matrix__class__][0] == StorageClass.Types.HOSTPATH:
        pytest.skip(msg="Skipping when storage is non-shared")


def wait_for_importer_container_message(importer_pod, msg):
    LOGGER.info(f"Wait for {importer_pod.name} container to show message: {msg}")
    try:
        sampled_msg = TimeoutSampler(
            timeout=120,
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
