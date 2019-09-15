"""
 CPU flags conftest
"""

import pytest
from utilities.infra import create_ns


@pytest.fixture(scope="module", autouse=True)
def cpu_features_namespace(unprivileged_client):
    yield from create_ns(client=unprivileged_client, name="cpu-features-test")
