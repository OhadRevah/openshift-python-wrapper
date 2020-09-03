# -*- coding: utf-8 -*-

"""
must gather test
"""

import logging
import os
import shutil
from subprocess import check_output

import pytest
import tests.network.utils as network_utils
import utilities.network
import yaml
from pytest_testconfig import config as py_config
from resources.configmap import ConfigMap
from resources.custom_resource_definition import CustomResourceDefinition
from resources.pod import Pod
from tests.must_gather import utils as mg_utils
from utilities.infra import create_ns
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
)


LOGGER = logging.getLogger(__name__)


class MissingResourceException(Exception):
    def __init__(self, resource):
        self.resource = resource

    def __str__(self):
        return f"No resources of type {self.resource} were found. Please check the test environment setup."


@pytest.fixture(scope="module")
def must_gather_image_url(cnv_current_version):
    if py_config["distribution"] == "upstream":
        return "quay.io/kubevirt/must-gather"

    must_gather_image = "container-native-virtualization-cnv-must-gather-rhel8"
    return f"registry-proxy.engineering.redhat.com/rh-osbs/{must_gather_image}:v{cnv_current_version}"


@pytest.fixture(scope="module")
def cnv_must_gather(
    tmpdir_factory,
    must_gather_image_url,
    must_gather_nad,
    nodenetworkstate_with_bridge,
    running_vm,
):
    """
    Run cnv-must-gather for data collection.
    """
    path = tmpdir_factory.mktemp("must_gather")
    try:
        must_gather_cmd = (
            f"oc adm must-gather --image={must_gather_image_url} --dest-dir={path}"
        )
        LOGGER.info(f"Running: {must_gather_cmd}")
        check_output(must_gather_cmd, shell=True)
        must_gather_log_dir = os.path.join(path, os.listdir(path)[0])
        yield must_gather_log_dir
    finally:
        shutil.rmtree(path)


@pytest.fixture(scope="module")
def custom_resource_definitions(default_client):
    yield list(CustomResourceDefinition.get(default_client))


@pytest.fixture(scope="module")
def kubevirt_crd_resources(default_client, custom_resource_definitions):
    kubevirt_resources = []
    for resource in custom_resource_definitions:
        if "kubevirt.io" in resource.instance.spec.group:
            kubevirt_resources.append(resource)
    return kubevirt_resources


@pytest.fixture(scope="module")
def must_gather_nad(rhel7_workers, rhel7_ovs_bridge, hco_namespace):
    with utilities.network.network_nad(
        nad_type=utilities.network.OVS
        if rhel7_workers
        else utilities.network.LINUX_BRIDGE,
        nad_name="mgnad",
        interface_name=rhel7_ovs_bridge if rhel7_workers else "mgbr",
        namespace=hco_namespace,
    ) as must_gather_nad:
        yield must_gather_nad


@pytest.fixture(scope="module")
def nodenetworkstate_with_bridge(
    rhel7_workers, rhel7_ovs_bridge, utility_pods, schedulable_nodes
):
    if rhel7_workers:
        yield rhel7_ovs_bridge
    else:
        with network_utils.network_device(
            interface_type=utilities.network.LINUX_BRIDGE,
            nncp_name="must-gather-br",
            interface_name="mgbr",
            network_utility_pods=utility_pods,
            nodes=schedulable_nodes,
        ) as br:
            yield br


@pytest.fixture(scope="module")
def running_hco_containers(default_client, hco_namespace):
    pods = []
    for pod in Pod.get(default_client, namespace=py_config["hco_namespace"]):
        for container in pod.instance["status"].get("containerStatuses", []):
            if container["ready"]:
                pods.append((pod, container))
    assert pods, f"No running pods in the {hco_namespace.name} namespace were found."
    return pods


@pytest.fixture(scope="module")
def skip_when_no_sriov(default_client):
    for crd in list(CustomResourceDefinition.get(default_client)):
        if crd.name == "sriovnetworknodestates.sriovnetwork.openshift.io":
            return
    pytest.skip(msg="Cluster without SR-IOV support")


@pytest.fixture(scope="module")
def node_gather_unprivileged_namespace(
    unprivileged_client, kmp_vm_label, default_client
):
    yield from create_ns(
        client=unprivileged_client,
        name="node-gather-unprivileged",
        kmp_vm_label=kmp_vm_label,
        admin_client=default_client,
    )


@pytest.fixture(scope="module")
def running_vm(node_gather_unprivileged_namespace, unprivileged_client):
    name = "vm"
    with VirtualMachineForTests(
        client=unprivileged_client,
        namespace=node_gather_unprivileged_namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
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
def config_maps_file(hco_namespace, cnv_must_gather):
    with open(
        f"{cnv_must_gather}/namespaces/{hco_namespace.name}/core/configmaps.yaml", "r",
    ) as config_map_file:
        return yaml.safe_load(config_map_file)
