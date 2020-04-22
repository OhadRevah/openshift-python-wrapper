"""
CDI Import
"""

import logging

import pytest
from resources.configmap import ConfigMap
from resources.persistent_volume_claim import PersistentVolumeClaim
from resources.storage_class import StorageClass


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
