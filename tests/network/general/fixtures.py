import pytest

from tests import utils as test_utils


@pytest.fixture(scope='class')
def create_linux_bridge(request):
    """
    Create needed linux bridges when setup is not bare-metal
    """
    bridge_name = test_utils.get_fixture_val(request=request, attr_name="bridge_name")

    def fin():
        """
        Remove created linux bridges
        """
        for pod in pytest.privileged_pods:
            pod_container = pod.containers()[0].name
            pod.execute(command=["ip", "link", "del", bridge_name], container=pod_container)
    request.addfinalizer(fin)

    for pod in pytest.privileged_pods:
        pod_container = pod.containers()[0].name
        pod.execute(
            command=["ip", "link", "add", bridge_name, "type", "bridge"], container=pod_container
        )
