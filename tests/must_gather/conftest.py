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
from ocp_resources.configmap import ConfigMap
from ocp_resources.custom_resource_definition import CustomResourceDefinition
from ocp_resources.pod import Pod
from pytest_testconfig import config as py_config

import utilities.network
from tests.must_gather import utils as mg_utils
from utilities.infra import ExecCommandOnPod, MissingResourceException, create_ns
from utilities.virt import VirtualMachineForTests, fedora_vm_body


LOGGER = logging.getLogger(__name__)


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
    output_file = os.path.join(path, "output.txt")
    try:
        must_gather_cmd = f"oc adm must-gather --image={must_gather_image_url} --dest-dir={path} &> {output_file}"
        LOGGER.info(f"Running: {must_gather_cmd}")
        check_output(must_gather_cmd, shell=True)
        must_gather_log_dir = mg_utils.get_log_dir(path=path)
        yield must_gather_log_dir
    finally:
        shutil.rmtree(path)


@pytest.fixture(scope="module")
def custom_resource_definitions(admin_client):
    yield list(CustomResourceDefinition.get(admin_client))


@pytest.fixture(scope="module")
def kubevirt_crd_resources(admin_client, custom_resource_definitions):
    kubevirt_resources = []
    for resource in custom_resource_definitions:
        if "kubevirt.io" in resource.instance.spec.group:
            kubevirt_resources.append(resource)
    return kubevirt_resources


@pytest.fixture(scope="module")
def must_gather_nad(hco_namespace):
    with utilities.network.network_nad(
        nad_type=utilities.network.LINUX_BRIDGE,
        nad_name="mgnad",
        interface_name="mgbr",
        namespace=hco_namespace,
    ) as must_gather_nad:
        yield must_gather_nad


@pytest.fixture(scope="module")
def nodenetworkstate_with_bridge(utility_pods, schedulable_nodes):
    with utilities.network.network_device(
        interface_type=utilities.network.LINUX_BRIDGE,
        nncp_name="must-gather-br",
        interface_name="mgbr",
        network_utility_pods=utility_pods,
        nodes=schedulable_nodes,
    ) as br:
        yield br


@pytest.fixture(scope="module")
def running_hco_containers(admin_client, hco_namespace):
    pods = []
    for pod in Pod.get(admin_client, namespace=hco_namespace.name):
        for container in pod.instance["status"].get("containerStatuses", []):
            if container["ready"]:
                pods.append((pod, container))
    assert pods, f"No running pods in the {hco_namespace.name} namespace were found."
    return pods


@pytest.fixture(scope="module")
def node_gather_unprivileged_namespace(unprivileged_client):
    yield from create_ns(
        unprivileged_client=unprivileged_client,
        name="node-gather-unprivileged",
    )


@pytest.fixture(scope="module")
def running_vm(node_gather_unprivileged_namespace, unprivileged_client):
    name = "vm"
    with VirtualMachineForTests(
        client=unprivileged_client,
        namespace=node_gather_unprivileged_namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.fixture(scope="function")
def resource_type(request, admin_client):
    resource_type = request.param
    if not next(resource_type.get(admin_client), None):
        raise MissingResourceException(resource_type.__name__)
    return resource_type


@pytest.fixture(scope="module")
def running_sriov_network_operator_containers(admin_client):
    pods_and_containers = []
    for pod in Pod.get(
        admin_client, namespace=mg_utils.SRIOV_NETWORK_OPERATOR_NAMESPACE
    ):
        for container in pod.instance["status"].get("containerStatuses", []):
            if container["ready"]:
                pods_and_containers.append((pod, container))
    assert pods_and_containers, "No sriov pods were found."
    return pods_and_containers


@pytest.fixture(scope="function")
def config_map_by_name(request, admin_client):
    cm_name, cm_namespace = request.param
    return ConfigMap(name=cm_name, namespace=cm_namespace)


@pytest.fixture(scope="module")
def config_maps_file(hco_namespace, cnv_must_gather):
    with open(
        f"{cnv_must_gather}/namespaces/{hco_namespace.name}/core/configmaps.yaml",
        "r",
    ) as config_map_file:
        return yaml.safe_load(config_map_file)


@pytest.fixture(scope="session")
def rhcos_workers(worker_node1, utility_pods):
    return (
        ExecCommandOnPod(utility_pods=utility_pods, node=worker_node1).release_info[
            "ID"
        ]
        == "rhcos"
    )


@pytest.fixture(scope="session")
def skip_no_rhcos(rhcos_workers):
    if not rhcos_workers:
        pytest.skip("test should run only on rhcos workers")
