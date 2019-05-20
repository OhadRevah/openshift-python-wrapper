import logging

import pytest
from openshift.dynamic.exceptions import NotFoundError
from pytest_testconfig import config as py_config

from resources.resource import Resource
from utilities import utils
from . import config

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope='class')
def network_cr_linux_bridge_br1(request, default_client):
    """
    Create linux bridge network CR named br1
    """
    template_conf = py_config['template_defaults']
    crd_yaml = 'tests/manifests/network/bridge-net.yml'
    name = "br1test"
    data = utils.generate_yaml_from_template(file_=crd_yaml, **template_conf)

    def fin():
        """
        Remove created network CR
        """
        try:
            Resource.delete_from_dict(
                dyn_client=default_client, data=data, namespace=config.NETWORK_NS
            )
        except NotFoundError:
            LOGGER.info(f"Network cr {name} not found")
    request.addfinalizer(fin)

    assert Resource.create_from_dict(
        dyn_client=default_client, data=data, namespace=config.NETWORK_NS
    )
    return name


@pytest.fixture(scope='class')
def network_cr_linux_bridge_br1vlan100(request, default_client):
    """
    Create linux bridge network CR named br1vlan100 with VLAN 100
    """
    template_conf = py_config['template_defaults']
    crd_yaml = 'tests/manifests/network/bridge-vlan-100-net.yml'
    name = "br1vlan100"
    data = utils.generate_yaml_from_template(file_=crd_yaml, **template_conf)

    def fin():
        """
        Remove created network CR
        """
        try:
            Resource.delete_from_dict(
                dyn_client=default_client, data=data, namespace=config.NETWORK_NS
            )
        except NotFoundError:
            LOGGER.info(f"Network cr {name} not found")
    request.addfinalizer(fin)

    assert Resource.create_from_dict(
        dyn_client=default_client, data=data, namespace=config.NETWORK_NS
    )
    return name


@pytest.fixture(scope='class')
def linux_bridge_br1(request, network_utility_pods):
    """
    Create linux bridge named br1
    """
    bridge_name = 'br1test'

    def fin():
        """
        Remove created linux bridge
        """
        for pod in network_utility_pods:
            pod_container = pod.containers()[0].name
            pod.execute(command=["ip", "link", "del", bridge_name], container=pod_container)
    request.addfinalizer(fin)

    for pod in network_utility_pods:
        pod_container = pod.containers()[0].name
        pod.execute(
            command=["ip", "link", "add", bridge_name, "type", "bridge"], container=pod_container
        )
