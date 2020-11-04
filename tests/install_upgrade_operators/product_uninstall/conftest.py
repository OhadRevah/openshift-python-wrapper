import pytest
from resources.kubevirt import KubeVirt


@pytest.fixture()
def kubevirt_resource(admin_client):
    for kv in KubeVirt.get(dyn_client=admin_client):
        return kv
