import logging
from collections import defaultdict

import pytest
from pytest_testconfig import config as py_config
from resources.cdi import CDI
from resources.daemonset import DaemonSet
from resources.deployment import Deployment
from resources.hyperconverged import HyperConverged
from resources.kubevirt import KubeVirt
from resources.network_addons_config import NetworkAddonsConfig
from resources.node import Node
from resources.pod import Pod
from resources.resource import ResourceEditor
from resources.ssp import SSP
from resources.virtual_machine_import_configs import VMImportConfig

from tests.install_upgrade_operators.node_component.utils import SELECTORS
from tests.install_upgrade_operators.utils import (
    DEFAULT_HCO_PROGRESSING_CONDITIONS,
    wait_for_hco_conditions,
)


LOGGER = logging.getLogger(__name__)


def get_daemonset_by_name(admin_client, daemonset_name):
    for ds in DaemonSet.get(
        dyn_client=admin_client,
        namespace=py_config["hco_namespace"],
        name=daemonset_name,
    ):
        return ds


def get_deployment_by_name(admin_client, deployment_name):
    for dp in Deployment.get(
        dyn_client=admin_client,
        namespace=py_config["hco_namespace"],
        name=deployment_name,
    ):
        return dp


@pytest.fixture(scope="session")
def workers(nodes):
    """
    Get worker nodes.

    schedulable node fixture is based on kubevirt.io label.
    This fixture is intended to be used for purposes when kubevirt
    itself is not yet installed.
    """
    return [
        node for node in nodes if "node-role.kubernetes.io/worker" in node.labels.keys()
    ]


def add_labels_to_nodes(nodes, node_labels):
    """
    This function is going to add label to each node.
    Returns a node_resources and dictionary of lableled nodes.
    """
    node_resources = []
    labels_on_nodes = {}
    for index, node in enumerate(nodes, start=1):
        labels = {key: f"{value}{index}" for key, value in node_labels.items()}
        node_resource = ResourceEditor(patches={node: {"metadata": {"labels": labels}}})
        node_resource.update(backup_resources=True)
        node_resources.append(node_resource)
        labels_on_nodes[node.name] = labels
    return node_resources, labels_on_nodes


@pytest.fixture(scope="class")
def node_placement_labels(
    admin_client,
    masters,
    workers,
):
    """
    Set Infra and Workloads Labels on the worker nodes and
    Set Operators Labels on the master nodes.

    This would help with Installing CNV components on specific nodes.
    It yields a dictionary key is node and value is a dictionary of labels.
    """
    master_labels = {"op-comp": "op"}
    worker_labels = {"infra-comp": "infra", "work-comp": "work"}
    worker_resources, worker_node_labels = add_labels_to_nodes(
        nodes=workers, node_labels=worker_labels
    )
    master_resources, master_node_labels = add_labels_to_nodes(
        nodes=masters, node_labels=master_labels
    )
    yield {**worker_node_labels, **master_node_labels}
    for master_resource in master_resources:
        master_resource.restore()
    for worker_resource in worker_resources:
        worker_resource.restore()


def create_dict_by_label(values):
    nl = {}
    for selector, label in SELECTORS:
        nl[label] = [
            key for key, labels in values.items() if labels.get(selector) == label
        ]
    return nl


@pytest.fixture(scope="class")
def expected_node_by_label(node_placement_labels):
    return create_dict_by_label(values=node_placement_labels)


@pytest.fixture(scope="class")
def np_nodes_labels_dict(admin_client):
    return {
        node.name: node.instance.metadata.labels
        for node in Node.get(dyn_client=admin_client)
    }


@pytest.fixture(scope="class")
def nodes_labeled(np_nodes_labels_dict):
    return create_dict_by_label(values=np_nodes_labels_dict)


@pytest.fixture()
def ssp_cr_spec(admin_client, hco_namespace):
    ssp_cr = list(
        SSP.get(
            dyn_client=admin_client,
            name="ssp-kubevirt-hyperconverged",
            namespace=hco_namespace.name,
        )
    )
    return ssp_cr[0].instance.to_dict()["spec"]


@pytest.fixture()
def kubevirt_node_labeller_spec_nodeselector(admin_client):
    kubevirt_node_labeller_spec = get_daemonset_by_name(
        admin_client=admin_client, daemonset_name="kubevirt-node-labeller"
    ).instance.to_dict()["spec"]["template"]["spec"]
    return kubevirt_node_labeller_spec.get("nodeSelector")


@pytest.fixture()
def virt_template_validator_spec_nodeselector(admin_client):
    virt_template_validator_spec = get_deployment_by_name(
        admin_client=admin_client, deployment_name="virt-template-validator"
    ).instance.to_dict()["spec"]["template"]["spec"]
    return virt_template_validator_spec.get("nodeSelector")


@pytest.fixture()
def vm_import_configs_spec(admin_client, hco_namespace):
    vm_import_config = list(
        VMImportConfig.get(
            dyn_client=admin_client,
            namespace=hco_namespace.name,
            name="vmimport-kubevirt-hyperconverged",
        )
    )
    return vm_import_config[0].instance.to_dict()["spec"]


@pytest.fixture()
def vm_import_controller_spec_nodeselector(admin_client):
    vm_import_controller_spec = get_deployment_by_name(
        admin_client=admin_client, deployment_name="vm-import-controller"
    ).instance.to_dict()["spec"]["template"]["spec"]
    return vm_import_controller_spec.get("nodeSelector")


@pytest.fixture()
def network_addon_config_spec_placement(admin_client):
    network_addon_config = list(
        NetworkAddonsConfig.get(dyn_client=admin_client, name="cluster")
    )
    return network_addon_config[0].instance.to_dict()["spec"]["placementConfiguration"]


@pytest.fixture()
def network_deployment_placement_list(admin_client):
    nodeselector_lists = []
    network_deployments = ["kubemacpool-mac-controller-manager", "nmstate-webhook"]
    for deployment in network_deployments:
        nw_deployment = get_deployment_by_name(
            admin_client=admin_client, deployment_name=deployment
        ).instance.to_dict()["spec"]["template"]["spec"]
        nodeselector_lists.append(nw_deployment.get("nodeSelector"))
    return nodeselector_lists


@pytest.fixture()
def network_daemonsets_placement_list(admin_client):
    nodeselector_lists = []
    network_daemonsets = [
        "bridge-marker",
        "kube-cni-linux-bridge-plugin",
        "nmstate-handler",
    ]
    for daemonset in network_daemonsets:
        nw_daemonset = get_daemonset_by_name(
            admin_client=admin_client, daemonset_name=daemonset
        ).instance.to_dict()["spec"]["template"]["spec"]
        nodeselector_lists.append(nw_daemonset.get("nodeSelector"))
    return nodeselector_lists


@pytest.fixture()
def kubevirt_hyperconverged_spec(admin_client, hco_namespace):
    kubevirt_hyperconverged = list(
        KubeVirt.get(
            dyn_client=admin_client,
            namespace=hco_namespace.name,
            name="kubevirt-kubevirt-hyperconverged",
        )
    )
    return kubevirt_hyperconverged[0].instance.to_dict()["spec"]


@pytest.fixture()
def virt_daemonset_nodeselector_comp(admin_client):
    virt_daemonset = get_daemonset_by_name(
        admin_client=admin_client, daemonset_name="virt-handler"
    ).instance.to_dict()["spec"]["template"]["spec"]
    return virt_daemonset.get("nodeSelector").get("work-comp")


@pytest.fixture()
def virt_deployment_nodeselector_comp_list(admin_client):
    nodeselector_lists = []
    virt_deployments = ["virt-api", "virt-controller"]
    for deployment in virt_deployments:
        virt_deployment = get_deployment_by_name(
            admin_client=admin_client, deployment_name=deployment
        ).instance.to_dict()["spec"]["template"]["spec"]
        nodeselector_lists.append(virt_deployment.get("nodeSelector").get("infra-comp"))
    return nodeselector_lists


@pytest.fixture()
def cdi_spec(admin_client, hco_namespace):
    cdi_kubevirt_hyperconverged = list(
        CDI.get(
            dyn_client=admin_client,
            namespace=hco_namespace.name,
            name="cdi-kubevirt-hyperconverged",
        )
    )
    return cdi_kubevirt_hyperconverged[0].instance.to_dict()["spec"]


@pytest.fixture()
def cdi_deployment_nodeselector_list(admin_client):
    nodeselector_lists = []
    cdi_deployments = ["cdi-apiserver", "cdi-deployment", "cdi-uploadproxy"]
    for deployment in cdi_deployments:
        cdi_deployment = get_deployment_by_name(
            admin_client=admin_client, deployment_name=deployment
        ).instance.to_dict()["spec"]["template"]["spec"]
        nodeselector_lists.append(cdi_deployment.get("nodeSelector"))
    return nodeselector_lists


@pytest.fixture()
def hco_pods_per_nodes(admin_client, hco_namespace):
    pods_per_nodes = defaultdict(list)
    for pod in Pod.get(dyn_client=admin_client, namespace=hco_namespace.name):
        pods_per_nodes[pod.node.name].append(pod.name)
    return pods_per_nodes


@pytest.fixture(scope="class")
def hyperconverged_with_node_placement(request, admin_client, hco_namespace):
    """
    Update HCO CR with infrastructure and workloads spec.
    """
    infra_placement = request.param["infra"]
    workloads_placement = request.param["workloads"]
    for hc in HyperConverged.get(
        dyn_client=admin_client,
        namespace=hco_namespace.name,
        name="kubevirt-hyperconverged",
    ):
        LOGGER.info("Updating HCO with node placement.")
        with ResourceEditor(
            patches={
                hc: {
                    "spec": {
                        "infra": infra_placement,
                        "workloads": workloads_placement,
                    }
                }
            }
        ) as reditor:
            LOGGER.info("Waiting for HCO to report progressing condition.")
            wait_for_hco_conditions(
                admin_client=admin_client, conditions=DEFAULT_HCO_PROGRESSING_CONDITIONS
            )
            LOGGER.info(
                "Waiting for all HCO conditions to detect that it's back to a stable configuration."
            )
            wait_for_hco_conditions(admin_client=admin_client)
            yield reditor

        LOGGER.info("Waiting for HCO to report progressing condition.")
        wait_for_hco_conditions(
            admin_client=admin_client, conditions=DEFAULT_HCO_PROGRESSING_CONDITIONS
        )
        LOGGER.info(
            "Waiting for all HCO conditions to detect that it's back to a stable configuration."
        )
        wait_for_hco_conditions(admin_client=admin_client)
