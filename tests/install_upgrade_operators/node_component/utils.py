SELECTORS = [
    ("infra-comp", "infra1"),
    ("infra-comp", "infra2"),
    ("infra-comp", "infra3"),
    ("work-comp", "work1"),
    ("work-comp", "work2"),
    ("work-comp", "work3"),
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
INFRA_PODS_COMPONENTS = [
    "virt-controller",
    "virt-template-validator",
    "vm-import-controller",
    "kubemacpool-mac-controller-manager",
    "nmstate-webhook",
    "cdi-apiserver",
    "cdi-deployment",
    "cdi-uploadproxy",
]
WORKLOADS_PODS_COMPONENTS = [
    "virt-handler",
    "bridge-marker",
    "kube-cni-linux-bridge-plugin",
    "kubevirt-node-labeller",
    "nmstate-handler",
]

OPERATOR_PODS_COMPONENTS = [
    "cdi-operator",
    "cluster-network-addons-operator",
    "hco-operator",
    "hco-webhook",
    "hostpath-provisioner-operator",
    "kubevirt-ssp-operator",
    "node-maintenance-operator",
    "virt-operator",
    "vm-import-operator",
]


def find_components_on_node(component_list, pods_on_node):
    """
    This function is used to check the Pod on given node.
    It breaks the loop once it finds Pod from the given list.
    """
    found_components = []
    missing_components = []
    for component_name in component_list:
        for pod_name in pods_on_node:
            if pod_name.startswith(component_name):
                found_components.append(component_name)
                break
        else:
            missing_components.append(component_name)
    return found_components, missing_components


def verify_all_components_on_node(component_list, node_name, hco_pods_per_node):
    found_components, missing_components = find_components_on_node(
        component_list=component_list, pods_on_node=hco_pods_per_node[node_name]
    )
    assert not (
        missing_components
    ), f"verified component {found_components}, failed components {missing_components}"


def verify_no_components_on_nodes(
    component_list,
    node_names,
    hco_pods_per_node,
):
    node_results = {}
    for node_name in node_names:
        found_components, missing_components = find_components_on_node(
            component_list=component_list, pods_on_node=hco_pods_per_node[node_name]
        )
        node_results[node_name] = {
            "found": found_components,
            "missing": missing_components,
        }

    nodes_with_components = {
        node_name: node_results[node_name]["found"]
        for node_name in node_names
        if node_results[node_name]["found"]
    }
    assert not nodes_with_components, f"node results {node_results}"


def verify_components_exist_only_on_selected_node(
    hco_pods_per_nodes,
    component_list,
    selected_node,
):
    unselected_nodes = [
        node_name
        for node_name in hco_pods_per_nodes.keys()
        if node_name != selected_node
    ]
    verify_all_components_on_node(
        component_list=component_list,
        node_name=selected_node,
        hco_pods_per_node=hco_pods_per_nodes,
    )
    verify_no_components_on_nodes(
        component_list=component_list,
        node_names=unselected_nodes,
        hco_pods_per_node=hco_pods_per_nodes,
    )
