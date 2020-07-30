import pytest
from resources.kubevirt import KubeVirt


@pytest.fixture()
def kubevirt_resource(default_client):
    for kv in KubeVirt.get(dyn_client=default_client):
        return kv
