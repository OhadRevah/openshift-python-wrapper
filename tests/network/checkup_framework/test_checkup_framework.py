import pytest

from tests.network.checkup_framework.utils import assert_successful_checkup


pytestmark = pytest.mark.usefixtures("framework_resources")


@pytest.mark.polarion("CNV-8446")
def test_checkup(latency_configmap, latency_job):
    assert_successful_checkup(configmap=latency_configmap, job=latency_job)
