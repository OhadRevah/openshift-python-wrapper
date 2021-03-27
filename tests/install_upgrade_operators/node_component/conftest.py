import logging

import pytest
from ocp_resources.node import Node
from ocp_resources.pod import Pod
from ocp_resources.resource import ResourceEditor
from ocp_resources.ssp import SSP
from ocp_resources.subscription import Subscription
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from ocp_resources.virtual_machine_import_configs import VMImportConfig

from tests.install_upgrade_operators.node_component.utils import (
    CNV_OPERATOR_PODS_COMPONENTS,
    SELECTORS,
    get_pod_per_nodes,
)
from tests.install_upgrade_operators.utils import (
    get_deployment_by_name,
    get_network_addon_config,
)
from utilities.constants import TIMEOUT_5MIN
from utilities.hco import add_labels_to_nodes, apply_np_changes, wait_for_hco_conditions
from utilities.infra import get_daemonset_by_name
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)


LOGGER = logging.getLogger(__name__)


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
def virt_template_validator_spec_nodeselector(admin_client, hco_namespace):
    virt_template_validator_spec = get_deployment_by_name(
        admin_client=admin_client,
        deployment_name="virt-template-validator",
        namespace_name=hco_namespace.name,
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
def vm_import_controller_spec_nodeselector(admin_client, hco_namespace):
    vm_import_controller_spec = get_deployment_by_name(
        admin_client=admin_client,
        deployment_name="vm-import-controller",
        namespace_name=hco_namespace.name,
    ).instance.to_dict()["spec"]["template"]["spec"]
    return vm_import_controller_spec.get("nodeSelector")


@pytest.fixture()
def network_addon_config_spec_placement(admin_client):
    return get_network_addon_config(admin_client=admin_client).instance.to_dict()[
        "spec"
    ]["placementConfiguration"]


@pytest.fixture()
def network_deployment_placement_list(admin_client, hco_namespace):
    nodeselector_lists = []
    network_deployments = ["kubemacpool-mac-controller-manager", "nmstate-webhook"]
    for deployment in network_deployments:
        nw_deployment = get_deployment_by_name(
            admin_client=admin_client,
            deployment_name=deployment,
            namespace_name=hco_namespace.name,
        ).instance.to_dict()["spec"]["template"]["spec"]
        nodeselector_lists.append(nw_deployment.get("nodeSelector"))
    return nodeselector_lists


@pytest.fixture()
def network_daemonsets_placement_list(admin_client, hco_namespace):
    nodeselector_lists = []
    network_daemonsets = [
        "bridge-marker",
        "kube-cni-linux-bridge-plugin",
        "nmstate-handler",
    ]
    for daemonset in network_daemonsets:
        nw_daemonset = get_daemonset_by_name(
            admin_client=admin_client,
            daemonset_name=daemonset,
            namespace_name=hco_namespace.name,
        ).instance.to_dict()["spec"]["template"]["spec"]
        nodeselector_lists.append(nw_daemonset.get("nodeSelector"))
    return nodeselector_lists


@pytest.fixture()
def virt_daemonset_nodeselector_comp(admin_client, hco_namespace):
    virt_daemonset = get_daemonset_by_name(
        admin_client=admin_client,
        daemonset_name="virt-handler",
        namespace_name=hco_namespace.name,
    ).instance.to_dict()["spec"]["template"]["spec"]
    return virt_daemonset.get("nodeSelector").get("work-comp")


@pytest.fixture()
def virt_deployment_nodeselector_comp_list(admin_client, hco_namespace):
    nodeselector_lists = []
    virt_deployments = ["virt-api", "virt-controller"]
    for deployment in virt_deployments:
        virt_deployment = get_deployment_by_name(
            admin_client=admin_client,
            deployment_name=deployment,
            namespace_name=hco_namespace.name,
        ).instance.to_dict()["spec"]["template"]["spec"]
        nodeselector_lists.append(virt_deployment.get("nodeSelector").get("infra-comp"))
    return nodeselector_lists


@pytest.fixture()
def cdi_deployment_nodeselector_list(admin_client, hco_namespace):
    nodeselector_lists = []
    cdi_deployments = ["cdi-apiserver", "cdi-deployment", "cdi-uploadproxy"]
    for deployment in cdi_deployments:
        cdi_deployment = get_deployment_by_name(
            admin_client=admin_client,
            deployment_name=deployment,
            namespace_name=hco_namespace.name,
        ).instance.to_dict()["spec"]["template"]["spec"]
        nodeselector_lists.append(cdi_deployment.get("nodeSelector"))
    return nodeselector_lists


@pytest.fixture()
def hco_pods_per_nodes(admin_client, hco_namespace):
    return get_pod_per_nodes(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture()
def hco_pods_per_nodes_after_altering_placement(
    admin_client, hco_namespace, alter_np_configuration
):
    return get_pod_per_nodes(admin_client=admin_client, hco_namespace=hco_namespace)


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
    hyperconverged_resource_scope_function,
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
    apply_np_changes(
        admin_client=admin_client,
        hco=hyperconverged_resource_scope_function,
        hco_namespace=hco_namespace,
        infra_placement=infra_placement,
        workloads_placement=workloads_placement,
    )
    yield


@pytest.fixture(scope="class")
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
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True, timeout=TIMEOUT_5MIN)
        vm.vmi.wait_until_running()
        wait_for_vm_interfaces(vmi=vm.vmi)
        yield vm


@pytest.fixture()
def delete_vm_after_placement(
    vm_placement_vm_work3,
):
    # Delete the VM created after checking it's placement on correct node.
    if vm_placement_vm_work3.instance:
        vm_placement_vm_work3.delete(wait=True)


def update_subscription_config(admin_client, hco_namespace, sub, config):
    reseditor = ResourceEditor(
        patches={
            sub: {
                "spec": {
                    "config": config,
                }
            }
        }
    )
    LOGGER.info("Updating CNV subscription with config.")
    reseditor.update()
    LOGGER.info("Waiting for CNV HCO to be Ready.")
    wait_for_hco_conditions(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        wait_timeout=TIMEOUT_5MIN,
        consecutive_checks_count=10,
    )
    LOGGER.info("Verify that there no terminating operator pods.")
    sample = None
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=20,
        func=get_terminating_operators_pods,
        admin_client=admin_client,
        hco_namespace=hco_namespace,
    )
    try:
        for sample in samples:
            if not sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Timeout waiting for terminating pods to be deleted {sample}.")
        raise


def apply_subscription_changes(
    admin_client, sub, hco_namespace, node_selector=None, tolerations=None
):
    """
    This method configures node placement for the CNV subscription. It set
    the spec.config.nodeSelector and/or the spec.config.tolerations fields.
    This method is called before node-placement subscription tests, within
    a fixture.
    """
    current_config = sub.instance.to_dict()["spec"].get("config")

    # no change is required, exit
    if (not current_config) and (not node_selector) and (not tolerations):
        return

    target_config = (current_config or {}).copy()
    if node_selector is not None:
        target_config["nodeSelector"] = node_selector
    if tolerations is not None:
        target_config["tolerations"] = tolerations

    if current_config == target_config:
        LOGGER.info("No actual changes to node placement configuration, skipping")
        return

    update_subscription_config(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        sub=sub,
        config=target_config,
    )


def apply_sub_config_changes(admin_client, sub, hco_namespace, config=None):
    """
    set the CNV subscription spec.config; node placement configuration are two
    fields within the spec.config object. This method is used to restore the
    whole object to the origin state as was before the test, as part of tear down.
    The config field may be None.
    """
    current_config = sub.instance.to_dict()["spec"].get("config")

    if current_config == config:
        LOGGER.info("No actual changes to node placement configuration, skipping")
        return
    update_subscription_config(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        sub=sub,
        config=config,
    )


@pytest.fixture(scope="class")
def cnv_subscription_scope_class(admin_client, hco_namespace):
    for sub in Subscription.get(
        dyn_client=admin_client,
        namespace=hco_namespace.name,
    ):
        return sub


@pytest.fixture()
def cnv_subscription_scope_function(admin_client, hco_namespace):
    """
    Retrieves the CNV subscription
    """
    for sub in Subscription.get(
        dyn_client=admin_client,
        namespace=hco_namespace.name,
    ):
        return sub


@pytest.fixture(scope="class")
def cnv_sub_resource_before_np(
    admin_client, hco_namespace, cnv_subscription_scope_class
):
    """
    Update HCO CR with infrastructure and workloads spec.
    """
    LOGGER.info(
        "Fetching CNV Subscription to save its initial node placement configuration "
    )
    initial_config = cnv_subscription_scope_class.instance.to_dict()["spec"].get(
        "config"
    )
    yield cnv_subscription_scope_class
    LOGGER.info("Revert to initial HCO node placement configuration ")
    apply_sub_config_changes(
        admin_client=admin_client,
        sub=cnv_subscription_scope_class,
        hco_namespace=hco_namespace,
        config=initial_config,
    )


@pytest.fixture()
def alter_cnv_sub_configuration(
    request,
    admin_client,
    hco_namespace,
    cnv_subscription_scope_function,
):
    """
    Update CNV subscription with node placement configurations.
    By design, this fixture will not revert back the configuration
    of CNV subscription to its initial configuration so that it can
    be used in subsequent tests.
    Passing a None "node_selector" or "tolerations" will keep the
    existing correspondent value.
    """
    apply_subscription_changes(
        admin_client=admin_client,
        sub=cnv_subscription_scope_function,
        hco_namespace=hco_namespace,
        node_selector=request.param.get("node_selector"),
        tolerations=request.param.get("tolerations"),
    )


@pytest.fixture()
def subscription_pods_per_nodes_after_altering_placement(
    admin_client,
    hco_namespace,
):
    return get_pod_per_nodes(admin_client=admin_client, hco_namespace=hco_namespace)


def get_terminating_operators_pods(admin_client, hco_namespace):
    """
    Check the operator pod which are flagged for deletion to make sure new pods are created.
    """
    return [
        pod
        for pod in Pod.get(dyn_client=admin_client, namespace=hco_namespace.name)
        if pod.name.startswith(tuple(CNV_OPERATOR_PODS_COMPONENTS))
        and pod.instance.metadata.get("deletionTimestamp") is not None
    ]
