# -*- coding: utf-8 -*-

"""
must gather test
"""

import logging
import os
import shutil
from subprocess import check_output

import pytest
import yaml
from pytest_testconfig import config as py_config
from resources.configmap import ConfigMap
from resources.custom_resource_definition import CustomResourceDefinition
from resources.daemonset import DaemonSet
from resources.pod import Pod
from resources.service_account import ServiceAccount
from tests.must_gather import utils as mg_utils
from utilities.infra import create_ns, generate_yaml_from_template
from utilities.network import (
    LinuxBridgeNetworkAttachmentDefinition,
    LinuxBridgeNodeNetworkConfigurationPolicy,
)
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
)


LOGGER = logging.getLogger(__name__)


class NodeGatherDaemonSet(DaemonSet):
    def _to_dict(self):
        res = super()._to_dict()
        res.update(
            generate_yaml_from_template(
                file_=os.path.join(os.path.dirname(__file__), "node-gather-ds.yaml")
            )
        )
        return res


class MissingResourceException(Exception):
    def __init__(self, resource):
        self.resource = resource

    def __str__(self):
        return f"No resources of type {self.resource} were found. Please check the test environment setup."


@pytest.fixture(scope="module")
def cnv_must_gather(
    tmpdir_factory,
    cnv_containers,
    network_attachment_definition,
    nodenetworkstate_with_bridge,
    running_vm,
):
    """
    Run cnv-must-gather for data collection.
    """
    if py_config["distribution"] == "upstream":
        image = "quay.io/kubevirt/must-gather"
    else:
        image = cnv_containers["container-native-virtualization-cnv-must-gather-rhel8"]

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
def node_gather_namespace():
    yield from create_ns(name="node-gather")


@pytest.fixture(scope="module")
def node_gather_serviceaccount(node_gather_namespace):
    with ServiceAccount(name="node-gather", namespace=node_gather_namespace.name) as sa:
        yield sa


@pytest.fixture(scope="module")
def node_gather_daemonset(node_gather_namespace, node_gather_serviceaccount):
    with NodeGatherDaemonSet(
        name="node-gather-daemonset", namespace=node_gather_namespace.name
    ) as ds:
        ds.wait_until_deployed()
        yield ds


@pytest.fixture(scope="module")
def node_gather_pods(default_client, node_gather_daemonset):
    yield list(
        Pod.get(
            default_client,
            namespace=node_gather_daemonset.namespace,
            label_selector="cnv-test=must-gather",
        )
    )


@pytest.fixture(scope="module")
def network_attachment_definition():
    cni_type = py_config["template_defaults"]["linux_bridge_cni_name"]
    with LinuxBridgeNetworkAttachmentDefinition(
        namespace=py_config["hco_namespace"],
        name="mgnad",
        bridge_name="mgbr",
        cni_type=cni_type,
    ) as network_attachment_definition:
        yield network_attachment_definition


@pytest.fixture(scope="module")
def nodenetworkstate_with_bridge(network_utility_pods):
    with LinuxBridgeNodeNetworkConfigurationPolicy(
        name="must-gather-br", bridge_name="mgbr", worker_pods=network_utility_pods
    ) as br:
        yield br


@pytest.fixture(scope="module")
def running_hco_containers(default_client):
    pods = []
    for pod in Pod.get(default_client, namespace=py_config["hco_namespace"]):
        for container in pod.instance["status"].get("containerStatuses", []):
            if container["ready"]:
                pods.append((pod, container))
    assert (
        pods
    ), f"No running pods in the {py_config['hco_namespace']} namespace were found."
    return pods


@pytest.fixture(scope="module")
def skip_when_no_sriov(default_client):
    # TODO: remove once sriov is supported in downstream
    if py_config["distribution"] == "downstream":
        pytest.skip(msg="Skipping sriov tests in downstream.")
    for crd in list(CustomResourceDefinition.get(default_client)):
        if crd.name == "sriovnetworknodestates.sriovnetwork.openshift.io":
            return
    raise MissingResourceException(CustomResourceDefinition)


@pytest.fixture(scope="module")
def node_gather_unprivileged_namespace(unprivileged_client):
    yield from create_ns(client=unprivileged_client, name="node-gather-unprivileged")


@pytest.fixture(scope="module")
def running_vm(node_gather_unprivileged_namespace, unprivileged_client):
    name = "vm"
    with VirtualMachineForTests(
        client=unprivileged_client,
        namespace=node_gather_unprivileged_namespace.name,
        name=name,
        body=fedora_vm_body(name),
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.fixture(scope="function")
def resource_type(request, default_client):
    resource_type = request.param
    if not next(resource_type.get(default_client), None):
        raise MissingResourceException(resource_type.__name__)
    return resource_type


@pytest.fixture(scope="module")
def running_sriov_network_operator_containers(default_client):
    pods_and_containers = []
    for pod in Pod.get(
        default_client, namespace=mg_utils.SRIOV_NETWORK_OPERATOR_NAMESPACE
    ):
        for container in pod.instance["status"].get("containerStatuses", []):
            if container["ready"]:
                pods_and_containers.append((pod, container))
    assert pods_and_containers, "No sriov pods were found."
    return pods_and_containers


@pytest.fixture(scope="function")
def config_map_by_name(request, default_client):
    cm_name, cm_namespace = request.param
    return ConfigMap(name=cm_name, namespace=cm_namespace)


@pytest.fixture(scope="module")
def config_maps_file(cnv_must_gather):
    with open(
        f"{cnv_must_gather}/namespaces/{py_config['hco_namespace']}/core/configmaps.yaml",
        "r",
    ) as config_map_file:
        return yaml.safe_load(config_map_file)
