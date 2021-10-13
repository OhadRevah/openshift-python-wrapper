import logging
from collections import defaultdict

from kubernetes.client.rest import ApiException
from ocp_resources.pod import Pod
from ocp_resources.resource import ResourceEditor
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from openshift.dynamic.exceptions import NotFoundError, ResourceNotFoundError

from tests.install_upgrade_operators.utils import wait_for_stabilize
from utilities.constants import TIMEOUT_5MIN
from utilities.hco import wait_for_hco_post_update_stable_state


LOGGER = logging.getLogger(__name__)

SELECTORS = [
    ("infra-comp", "infra1"),
    ("infra-comp", "infra2"),
    ("infra-comp", "infra3"),
    ("work-comp", "work1"),
    ("work-comp", "work2"),
    ("work-comp", "work3"),
    ("op-comp", "op1"),
    ("op-comp", "op2"),
    ("op-comp", "op3"),
]

INFRA_LABEL_1 = {"nodePlacement": {"nodeSelector": {"infra-comp": "infra1"}}}
INFRA_LABEL_2 = {"nodePlacement": {"nodeSelector": {"infra-comp": "infra2"}}}
INFRA_LABEL_3 = {"nodePlacement": {"nodeSelector": {"infra-comp": "infra3"}}}
WORK_LABEL_1 = {"nodePlacement": {"nodeSelector": {"work-comp": "work1"}}}
WORK_LABEL_2 = {"nodePlacement": {"nodeSelector": {"work-comp": "work2"}}}
WORK_LABEL_3 = {"nodePlacement": {"nodeSelector": {"work-comp": "work3"}}}

SUBSCRIPTION_NODE_SELCTOR_1 = {"op-comp": "op1"}
SUBSCRIPTION_NODE_SELCTOR_2 = {"op-comp": "op2"}
SUBSCRIPTION_NODE_SELCTOR_3 = {"op-comp": "op3"}
SUBSCRIPTION_TOLERATIONS = [
    {
        "effect": "NoSchedule",
        "key": "node-role.kubernetes.io/master",
        "operator": "Exists",
    }
]


NODE_PLACEMENT_INFRA = {
    "nodePlacement": {
        "affinity": {
            "nodeAffinity": {
                "requiredDuringSchedulingIgnoredDuringExecution": {
                    "nodeSelectorTerms": [
                        {
                            "matchExpressions": [
                                {
                                    "key": "infra-comp",
                                    "operator": "In",
                                    "values": ["infra1", "infra2"],
                                }
                            ]
                        }
                    ]
                }
            }
        },
        "nodeSelector": {"infra-comp": "infra1"},
        "tolerations": [
            {
                "effect": "NoSchedule",
                "key": "node-role.kubernetes.io/worker",
                "operator": "Exists",
            }
        ],
    }
}

NODE_PLACEMENT_WORKLOADS = {
    "nodePlacement": {
        "affinity": {
            "nodeAffinity": {
                "preferredDuringSchedulingIgnoredDuringExecution": [
                    {
                        "preference": {
                            "matchExpressions": [
                                {
                                    "key": "work-comp",
                                    "operator": "In",
                                    "values": ["work1", "work2"],
                                }
                            ]
                        },
                        "weight": 1,
                    }
                ],
                "requiredDuringSchedulingIgnoredDuringExecution": {
                    "nodeSelectorTerms": [
                        {
                            "matchExpressions": [
                                {
                                    "key": "work-comp",
                                    "operator": "In",
                                    "values": ["work1", "work2"],
                                }
                            ]
                        }
                    ]
                },
            }
        },
        "nodeSelector": {"work-comp": "work2"},
        "tolerations": [
            {
                "effect": "NoSchedule",
                "key": "node-role.kubernetes.io/worker",
                "operator": "Exists",
            }
        ],
    }
}

# Below list consists of Infrastructure and Workloads pods based on Daemonset and Deployments.
CNV_INFRA_PODS_COMPONENTS = [
    "virt-controller",
    "virt-template-validator",
    "vm-import-controller",
    "kubemacpool-mac-controller-manager",
    "nmstate-webhook",
    "cdi-apiserver",
    "cdi-deployment",
    "cdi-uploadproxy",
]
CNV_WORKLOADS_PODS_COMPONENTS = [
    "virt-handler",
    "bridge-marker",
    "kube-cni-linux-bridge-plugin",
    "nmstate-handler",
]

CNV_OPERATOR_PODS_COMPONENTS = [
    "cdi-operator",
    "cluster-network-addons-operator",
    "hco-operator",
    "hco-webhook",
    "ssp-operator",
    "node-maintenance-operator",
    "virt-operator",
    "vm-import-operator",
]


def find_components_on_node(component_list, node_name, admin_client, hco_namespace):
    """
    This function is used to check the Pod on given node. It breaks the loop once it finds Pod from the given list.

    Args:
        component_list (list): list of components to be matched
        node_name (str): Name of the node
        admin_client(DynamicClient): DynamicClient object
        hco_namespace(Namespace): Namespace object

    Returns:
        list, list: list of matched components, list of unmatched components for a given node
    """
    pods_on_node = get_pod_per_nodes(
        admin_client=admin_client, hco_namespace=hco_namespace
    )
    found_components = []
    missing_components = []
    if node_name not in pods_on_node:
        LOGGER.warning(f"Node: {node_name}, does not have any associated pods.")
        return found_components, missing_components
    for component_name in component_list:
        for pod_name in pods_on_node[node_name]:
            if pod_name.startswith(component_name):
                found_components.append(component_name)
                break
        else:
            missing_components.append(component_name)
    LOGGER.info(
        f"For node: {node_name}, found components: {found_components}, "
        f"missing components: {missing_components}"
    )
    return found_components, missing_components


def verify_all_components_on_node(
    component_list, node_name, admin_client, hco_namespace
):
    """
    This function validates that actual pods associated with a given node matches with the list of expected pods for
    same node

    Args:
        component_list (list): list of components to be matched
        node_name (str): Name of the node
        admin_client(DynamicClient): DynamicClient object
        hco_namespace(Namespace): Namespace object

    raise:
        TimeoutExpiredError: if a match is not found
    """
    LOGGER.info(
        f"Validating that following pod types: {component_list} are present for node: {node_name}"
    )
    samples = TimeoutSampler(
        wait_timeout=300,
        sleep=5,
        func=find_components_on_node,
        component_list=component_list,
        node_name=node_name,
        admin_client=admin_client,
        hco_namespace=hco_namespace,
    )
    found_components = None
    missing_components = None

    try:
        for found_components, missing_components in samples:
            if not missing_components:
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"For Node:{node_name}, verified components {found_components}, "
            f"failed components {missing_components}"
        )
        raise


def verify_no_components_on_nodes(
    component_list,
    node_names,
    admin_client,
    hco_namespace,
):
    """
    This function validates that a list of pods are not associated with any of node from a given list

    Args:
        component_list (list): list of components to be matched
        node_names (list): Name of the nodes
        admin_client(DynamicClient): DynamicClient object
        hco_namespace(Namespace): Namespace object

    raise:
        TimeoutExpiredError: if a match is found
    """
    LOGGER.info(
        f"Validating following pod types: {component_list} are not present on nodes: {node_names}"
    )

    def _check_found_components_all_nodes():
        node_results = {}
        for node_name in node_names:
            found_components, missing_components = find_components_on_node(
                component_list=component_list,
                node_name=node_name,
                admin_client=admin_client,
                hco_namespace=hco_namespace,
            )
            node_results[node_name] = {
                "found": found_components,
                "missing": missing_components,
            }
            LOGGER.debug(
                f"On node: {node_name}, found: {found_components}, missing_components: {missing_components}"
            )

        return {
            node_name: node_results[node_name]["found"]
            for node_name in node_names
            if node_results[node_name]["found"]
        }

    samples = TimeoutSampler(
        wait_timeout=200,
        sleep=5,
        func=_check_found_components_all_nodes,
    )
    sample = None
    try:
        for sample in samples:
            if not sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"Timed out waiting for no matching components on nodes:{node_names}, actual results {sample}"
        )
        raise


def verify_components_exist_only_on_selected_node(
    hco_pods_per_nodes,
    component_list,
    selected_node,
    admin_client,
    hco_namespace,
):
    """
    This function validates only expected pods have been spin'ed up on a given node.

    Args:
        hco_pods_per_nodes(dict): dictionary with node names as keys and associated list of pod apps as values
        component_list (list): list of components to be matched
        selected_node (str): Name of the selected node
        admin_client(DynamicClient): DynamicClient object
        hco_namespace(Namespace): Namespace object
    """
    unselected_nodes = [
        node_name
        for node_name in hco_pods_per_nodes.keys()
        if node_name != selected_node
    ]
    verify_all_components_on_node(
        component_list=component_list,
        node_name=selected_node,
        admin_client=admin_client,
        hco_namespace=hco_namespace,
    )
    verify_no_components_on_nodes(
        component_list=component_list,
        node_names=unselected_nodes,
        admin_client=admin_client,
        hco_namespace=hco_namespace,
    )


def get_pod_per_nodes(admin_client, hco_namespace):
    """
    This function creates a dictionary, with nodes as keys and associated list of pod apps as values

    Args:
        admin_client(DynamicClient): DynamicClient object
        hco_namespace(Namespace): Namespace object

    Returns:
        dict: a dictionary, with nodes as keys and associated list of pod apps as values
    """

    def _get_pods_per_nodes():
        pods_per_nodes = defaultdict(list)
        for pod in Pod.get(
            dyn_client=admin_client,
            namespace=hco_namespace.name,
        ):
            try:
                # field_selector="status.phase==Running" is not always reliable
                # to filter out terminating pods, see: https://github.com/kubernetes/kubectl/issues/450
                if pod.instance.metadata.get("deletionTimestamp") is None:
                    pods_per_nodes[pod.node.name].append(pod)
            except ApiException as ex:
                if ex.reason == ResourceNotFoundError:
                    LOGGER.debug(
                        f"Ignoring pods that disappeared during the query. node={pod.node.name} pod={pod.name}"
                    )
        return pods_per_nodes

    pod_names_per_nodes = {}
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=30,
        func=_get_pods_per_nodes,
        exceptions_dict={NotFoundError: []},
    )
    try:
        for sample in samples:
            if all(
                pod.exists and pod.status == Pod.Status.RUNNING
                for pods in sample.values()
                for pod in pods
            ):
                pod_names_per_nodes = {
                    node: [pod.name for pod in pods] for node, pods in sample.items()
                }
                return pod_names_per_nodes
    except TimeoutExpiredError:
        LOGGER.error(f"Timeout waiting for pods to be ready {pod_names_per_nodes}.")
        raise


def update_subscription_config(admin_client, hco_namespace, subscription, config):
    """
    Updates CNV subscription spec.config

    Args:
        admin_client(DynamicClient): DynamicClient object
        hco_namespace (Resource): hco_namespace
        subscription(Resource): subscription resource
        config(dict): config dict to be used for patch operation

    Raises:
        TimeoutExpiredError: if appropriate pods are not re-spinned
    """
    editor = ResourceEditor(
        patches={
            subscription: {
                "spec": {
                    "config": config,
                }
            }
        },
    )
    editor.update(backup_resources=False)

    LOGGER.info("Waiting for CNV HCO to be Ready.")
    wait_for_stabilize(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        wait_timeout=TIMEOUT_5MIN,
        consecutive_checks_count=10,
    )

    wait_for_hco_post_update_stable_state(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
    )
