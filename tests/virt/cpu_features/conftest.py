"""
 CPU flags conftest
"""

import pytest
from resources.namespace import Namespace


@pytest.fixture(scope="module", autouse=True)
def cpu_features_namespace():
    with Namespace(name="cpu-features-test") as ns:
        ns.wait_for_status(status=Namespace.Status.ACTIVE)
        yield ns
