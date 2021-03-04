import pytest
from ocp_resources.cluster_service_version import ClusterServiceVersion


@pytest.fixture()
def csv(admin_client):
    for csv in ClusterServiceVersion.get(
        dyn_client=admin_client, namespace="openshift-cnv"
    ):
        return csv
