"""
CDI Import
"""

import logging

import pytest

from tests.storage.constants import HPP_STORAGE_CLASSES


LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def skip_non_shared_storage(storage_class_matrix__function__):
    if [*storage_class_matrix__function__][0] in HPP_STORAGE_CLASSES:
        pytest.skip(msg="Skipping when storage is non-shared")
