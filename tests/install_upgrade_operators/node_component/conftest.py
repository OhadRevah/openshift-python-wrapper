import logging
from collections import defaultdict

import pytest
from kubernetes.client.rest import ApiException
from openshift.dynamic.exceptions import ResourceNotFoundError
from pytest_testconfig import config as py_config
from resources.cdi import CDI
from resources.daemonset import DaemonSet
from resources.deployment import Deployment
from resources.kubevirt import KubeVirt
from resources.network_addons_config import NetworkAddonsConfig
from resources.node import Node
from resources.pod import Pod
from resources.resource import ResourceEditor
from resources.ssp import SSP
from resources.utils import TimeoutExpiredError, TimeoutSampler
from resources.virtual_machine_import_configs import VMImportConfig

from tests.install_upgrade_operators.node_component.utils import SELECTORS
from tests.install_upgrade_operators.utils import (
    DEFAULT_HCO_CONDITIONS,
    DEFAULT_HCO_PROGRESSING_CONDITIONS,
    wait_for_hco_conditions,
)
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
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


def get_pod_per_nodes(admin_client, hco_namespace):
    LOGGER.info("Getting list of pods per nodes.")
    pods_per_nodes = defaultdict(list)
    for pod in Pod.get(
        dyn_client=admin_client,
        namespace=hco_namespace.name,
    ):
        try:
            # field_selector="status.phase==Running" is not always reliable
            # to filter out terminating pods, see: https://github.com/kubernetes/kubectl/issues/450
            if pod.instance.metadata.get("deletionTimestamp") is None:
                pods_per_nodes[pod.node.name].append(pod.name)
        except ApiException as ex:
            if ex.reason == ResourceNotFoundError:
                LOGGER.debug(
                    "Ignoring pods that disappeared in the middle of the query."
                )
    LOGGER.info(f"Current placement: {pods_per_nodes}")
    return pods_per_nodes


@pytest.fixture()
def hco_pods_per_nodes(admin_client, hco_namespace):
    return get_pod_per_nodes(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture()
def hco_pods_per_nodes_after_altering_placement(
    admin_client, hco_namespace, alter_np_configuration
):
    return get_pod_per_nodes(admin_client=admin_client, hco_namespace=hco_namespace)


def apply_np_changes(
    admin_client, hco, hco_namespace, infra_placement=None, workloads_placement=None
):
    current_infra = hco.instance.to_dict()["spec"].get("infra")
    current_workloads = hco.instance.to_dict()["spec"].get("workloads")
    target_infra = infra_placement if infra_placement is not None else current_infra
    target_workloads = (
        workloads_placement if workloads_placement is not None else current_workloads
    )
    if target_workloads != current_workloads or target_infra != current_infra:
        reseditor = ResourceEditor(
            patches={
                hco: {
                    "spec": {
                        "infra": target_infra or None,
                        "workloads": target_workloads or None,
                    }
                }
            }
        )
        LOGGER.info("Updating HCO with node placement.")
        reseditor.update()
        LOGGER.info("Waiting for HCO to report progressing condition.")
        wait_for_hco_conditions(
            admin_client=admin_client,
            conditions=DEFAULT_HCO_PROGRESSING_CONDITIONS,
            sleep=5,
        )
        LOGGER.info(
            "Waiting for all HCO conditions to detect that it's back to a stable configuration."
        )
        wait_for_hco_conditions(
            admin_client=admin_client,
            conditions=DEFAULT_HCO_CONDITIONS,
            sleep=5,
            number_of_consecutive_checks=6,
        )
        # unfortunately at this time we are not really done:
        # HCO propagated the change to components operators that propagated it
        # to their operands (deployments and daemonsets)
        # so all the CNV operators reports progressing=False and even HCO reports progressing=False
        # but deployment and daemonsets controllers has still to kill and restart pods.
        # with the following lines we can wait for all the deployment and daemonsets in
        # openshift-cnv namespace to be back to uptodate status.
        # The remain issue is that if we check it too fast, we can even check before
        # deployment and daemonsets controller report uptodate=false.
        # We have also to compare the observedGeneration with the generation number
        # to be sure that the relevant controller already updated the status
        for ds in DaemonSet.get(
            dyn_client=admin_client,
            namespace=hco_namespace.name,
        ):
            wait_for_ds(ds=ds)
        for dp in Deployment.get(
            dyn_client=admin_client,
            namespace=hco_namespace.name,
        ):
            wait_for_dp(dp=dp)
    else:
        LOGGER.info("No actual changes to node placement configuration, skipping")


def wait_for_dp(dp):
    LOGGER.info(f"Waiting for deployment {dp.name} to be up to date.")
    samples = TimeoutSampler(
        timeout=240,
        sleep=5,
        func=lambda: dp.instance.to_dict(),
    )
    try:
        for sample in samples:
            status = sample.get("status")
            metadata = sample.get("metadata")
            if metadata.get("generation") == status.get(
                "observedGeneration"
            ) and status.get("replicas") == status.get("updatedReplicas"):
                break
    except TimeoutExpiredError:
        LOGGER.error(f"Timeout waiting for deployment {dp.name} to be up to date.")
        raise


def wait_for_ds(ds):
    LOGGER.info(f"Waiting for daemonset {ds.name} to be up to date.")
    samples = TimeoutSampler(
        timeout=240,
        sleep=5,
        func=lambda: ds.instance.to_dict(),
    )
    try:
        for sample in samples:
            status = sample.get("status")
            metadata = sample.get("metadata")
            if metadata.get("generation") == status.get("observedGeneration") and (
                status.get("desiredNumberScheduled")
                == status.get("currentNumberScheduled")
                == status.get("updatedNumberScheduled")
            ):
                break
    except TimeoutExpiredError:
        LOGGER.error(f"Timeout waiting for daemonset {ds.name} to be up to date.")
        raise


@pytest.fixture(scope="class")
def hyperconverged_with_node_placement(
    request, admin_client, hco_namespace, hyperconverged_resource_scope_class
):
    """
    Update HCO CR with infrastructure and workloads spec.
    """
    infra_placement = request.param["infra"]
    workloads_placement = request.param["workloads"]

    LOGGER.info("Fetching HCO to save its initial node placement configuration ")
    initial_infra = hyperconverged_resource_scope_class.instance.to_dict()["spec"].get(
        "infra", {}
    )
    initial_workloads = hyperconverged_resource_scope_class.instance.to_dict()[
        "spec"
    ].get("workloads", {})
    yield apply_np_changes(
        admin_client=admin_client,
        hco=hyperconverged_resource_scope_class,
        hco_namespace=hco_namespace,
        infra_placement=infra_placement,
        workloads_placement=workloads_placement,
    )
    LOGGER.info("Revert to initial HCO node placement configuration ")
    apply_np_changes(
        admin_client=admin_client,
        hco=hyperconverged_resource_scope_class,
        hco_namespace=hco_namespace,
        infra_placement=initial_infra,
        workloads_placement=initial_workloads,
    )


@pytest.fixture(scope="class")
def hyperconverged_resource_before_np(
    admin_client, hco_namespace, hyperconverged_resource_scope_class
):
    """
    Update HCO CR with infrastructure and workloads spec.
    """
    LOGGER.info("Fetching HCO to save its initial node placement configuration ")
    initial_infra = hyperconverged_resource_scope_class.instance.to_dict()["spec"].get(
        "infra", {}
    )
    initial_workloads = hyperconverged_resource_scope_class.instance.to_dict()[
        "spec"
    ].get("workloads", {})
    yield hyperconverged_resource_scope_class
    LOGGER.info("Revert to initial HCO node placement configuration ")
    apply_np_changes(
        admin_client=admin_client,
        hco=hyperconverged_resource_scope_class,
        hco_namespace=hco_namespace,
        infra_placement=initial_infra,
        workloads_placement=initial_workloads,
    )


@pytest.fixture()
def alter_np_configuration(
    request,
    admin_client,
    hco_namespace,
    hyperconverged_resource,
):
    """
    Update HCO CR with infrastructure and workloads spec.
    By design, this fixture will not revert back the configuration
    of HCO CR to its initial configuration so that it can be used in
    subsequent tests.
    Passing a None "infra" or "workloads" will keep the existing correspondent value.
    """
    infra_placement = request.param.get("infra")
    workloads_placement = request.param.get("workloads")
    yield apply_np_changes(
        admin_client=admin_client,
        hco=hyperconverged_resource,
        hco_namespace=hco_namespace,
        infra_placement=infra_placement,
        workloads_placement=workloads_placement,
    )


@pytest.fixture()
def vm_placement_vm_work3(
    namespace,
    unprivileged_client,
    nodes_labeled,
):
    name = "vm-placement-sanity-tests-vm"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=nodes_labeled["work3"][0],
        cloud_init_data=FEDORA_CLOUD_INIT_PASSWORD,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True, timeout=300)
        vm.vmi.wait_until_running()
        wait_for_vm_interfaces(vmi=vm.vmi)
        yield vm