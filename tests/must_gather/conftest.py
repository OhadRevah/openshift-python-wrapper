# -*- coding: utf-8 -*-

"""
must gather test
"""

import logging
import os
import shutil
from subprocess import check_output

import pytest
from pytest_testconfig import config as py_config
from resources.daemonset import DaemonSet
from resources.network_attachment_definition import (
    LinuxBridgeNetworkAttachmentDefinition,
)
from resources.pod import Pod
from resources.service_account import ServiceAccount
from tests import utils as test_utils
from utilities import utils


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def cnv_must_gather(
    tmpdir_factory,
    cnv_containers,
    network_attachment_definition,
    nodenetworkstate_with_bridge,
):
    """
    Run cnv-must-gather for data collection.
    """
    if py_config["distribution"] == "upstream":
        image = "quay.io/kubevirt/must-gather"
    else:
        image = cnv_containers["cnv-must-gather"]

    path = tmpdir_factory.mktemp("must_gather")
    try:
        must_gather_cmd = f"oc adm must-gather --image={image} --dest-dir={path}"
        LOGGER.info(f"Running: {must_gather_cmd}")
        check_output(must_gather_cmd, shell=True)
        must_gather_log_dir = os.path.join(path, os.listdir(path)[0])
        yield must_gather_log_dir
    finally:
        shutil.rmtree(path)


@pytest.fixture(scope="module")
def node_gather_namespace(default_client):
    yield from test_utils.create_ns(client=default_client, name="node-gather")


@pytest.fixture(scope="module")
def node_gather_serviceaccount(node_gather_namespace):
    with ServiceAccount(name="node-gather", namespace=node_gather_namespace.name) as sa:
        yield sa


class NodeGatherDaemonSet(DaemonSet):
    def _to_dict(self):
        res = super()._to_dict()
        res.update(
            utils.generate_yaml_from_template(
                file_=os.path.join(os.path.dirname(__file__), "node-gather-ds.yaml")
            )
        )
        return res


@pytest.fixture(scope="module")
def node_gather_daemonset(node_gather_namespace, node_gather_serviceaccount):
    with NodeGatherDaemonSet(
        name="node-gather-daemonset", namespace=node_gather_namespace.name
    ) as ds:
        ds.wait_until_deployed()
        yield ds


@pytest.fixture(scope="module")
def node_gather_pods(default_client, node_gather_daemonset):
    yield list(Pod.get(default_client, namespace=node_gather_daemonset.namespace))


@pytest.fixture(scope="module")
def network_attachment_definition(node_gather_namespace):
    cni_type = py_config["template_defaults"]["linux_bridge_cni_name"]
    with LinuxBridgeNetworkAttachmentDefinition(
        namespace=node_gather_namespace.name,
        name="mgnad",
        bridge_name="mgbr",
        cni_type=cni_type,
    ) as network_attachment_definition:
        yield network_attachment_definition


@pytest.fixture(scope="module")
def nodenetworkstate_with_bridge(network_utility_pods):
    with test_utils.LinuxBridgeNodeNetworkConfigurationPolicy(
        name="must-gather-br", bridge_name="mgbr", worker_pods=network_utility_pods
    ) as br:
        yield br
