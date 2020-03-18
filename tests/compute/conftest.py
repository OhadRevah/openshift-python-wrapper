# -*- coding: utf-8 -*-

import logging

import pytest
from resources.persistent_volume_claim import PersistentVolumeClaim


LOGGER = logging.getLogger(__name__)


"""
General tests fixtures
"""


@pytest.fixture()
def skip_migration_access_mode_rwo(storage_class_matrix__class__):
    if (
        storage_class_matrix__class__[[*storage_class_matrix__class__][0]][
            "access_mode"
        ]
        == PersistentVolumeClaim.AccessMode.RWO
    ):
        pytest.skip(
            msg="Skipping migration when access_mode is RWO; cannot migrate VMI with non-shared PVCs"
        )
