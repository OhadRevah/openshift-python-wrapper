import pytest
from ocp_resources.api_service import APIService
from ocp_resources.configmap import ConfigMap
from ocp_resources.custom_resource_definition import CustomResourceDefinition
from ocp_resources.daemonset import DaemonSet
from ocp_resources.deployment import Deployment
from ocp_resources.mutating_webhook_config import MutatingWebhookConfiguration
from ocp_resources.package_manifest import PackageManifest
from ocp_resources.pod import Pod
from ocp_resources.replicaset import ReplicaSet
from ocp_resources.role_binding import RoleBinding
from ocp_resources.secret import Secret
from ocp_resources.security_context_constraints import SecurityContextConstraints
from ocp_resources.service import Service
from ocp_resources.service_account import ServiceAccount
from ocp_resources.validating_webhook_config import ValidatingWebhookConfiguration

import utilities.network
from utilities.infra import (
    BUG_STATUS_CLOSED,
    get_bug_status,
    get_bugzilla_connection_params,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body


pytestmark = pytest.mark.sno

RESOURCE_TYPES = [
    APIService,
    ConfigMap,
    CustomResourceDefinition,
    DaemonSet,
    Deployment,
    MutatingWebhookConfiguration,
    PackageManifest,
    Pod,
    ReplicaSet,
    RoleBinding,
    Secret,
    SecurityContextConstraints,
    Service,
    ServiceAccount,
    ValidatingWebhookConfiguration,
]
EXPECTED_CNAO_COMP_NAMES = [
    "multus",
    "nmstate-handler",
    "cluster-network-addons-operator",
    "kubemacpool",
    "bridge",
    "nmstate",
    "ovs-cni",
]
EXPECTED_CNAO_COMP = [
    "multus",
    "NMSTATE_HANDLER_IMAGE",
    "cnao",
    "kubeMacPool",
    "linuxBridge",
    "nmstate",
    "ovs",
]
COMP_LABELS = ["component", "version", "part-of", "managed-by"]
MANAGED_BY = "managed-by"
OLM = "olm"
IGNORE_LIST = [
    "token",
    "metrics",
    "lock",
    "configmap/5",
    "lease",
    "dockercfg",
    "apiservice",
    "validatingwebhook",
    "packagemanifest",
]
KNOWN_BUG = "ServiceAccount/cluster-network-addons-operator"


class UnaccountedComponents(Exception):
    def __init__(self, components):
        self.components = components

    def __str__(self):
        return f"{self.components} are unaccounted CNAO components. Check if relevent. if so, modify test"


def get_all_network_resources(dyn_client, namespace):
    # Extract all related resources, iterating through each resource type
    return [
        resource
        for _type in RESOURCE_TYPES
        for resource in _type.get(dyn_client=dyn_client, namespace=namespace)
        if any(component in resource.name for component in EXPECTED_CNAO_COMP_NAMES)
    ]


def filter_resources(resources, network_addons_config, is_post_cnv_upgrade_cluster):
    bad_rcs = []
    for resource in resources:
        if KNOWN_BUG in f"{resource.kind}/{resource.name}" and (
            get_bug_status(
                bugzilla_connection_params=get_bugzilla_connection_params(), bug=1995606
            )
            not in BUG_STATUS_CLOSED
        ):
            continue
        if any(
            ignore in f"{resource.kind}/{resource.name}".lower()
            for ignore in IGNORE_LIST
        ) or ("Secret" in resource.kind and is_post_cnv_upgrade_cluster):
            continue
        try:
            for key in COMP_LABELS:
                if (
                    network_addons_config.labels[
                        f"{resource.ApiGroup.APP_KUBERNETES_IO}/{key}"
                    ]
                    not in resource.labels[
                        f"{resource.ApiGroup.APP_KUBERNETES_IO}/{key}"
                    ]
                ):
                    if (
                        MANAGED_BY in key
                        and "cluster-network-addons-operator" in resource.name
                        and resource.labels[
                            f"{resource.ApiGroup.APP_KUBERNETES_IO}/{key}"
                        ]
                        == OLM
                    ):
                        continue

                    bad_rcs.append(f"{resource.kind}/{resource.name}")
        except (KeyError, TypeError):
            bad_rcs.append(f"{resource.kind}/{resource.name}")

    return bad_rcs


def verify_cnao_labels(
    admin_client, namespace, network_addons_config, is_post_cnv_upgrade_cluster
):
    cnao_resources = get_all_network_resources(
        dyn_client=admin_client, namespace=namespace
    )
    bad_rcs = filter_resources(
        resources=cnao_resources,
        network_addons_config=network_addons_config,
        is_post_cnv_upgrade_cluster=is_post_cnv_upgrade_cluster,
    )

    assert not bad_rcs, f"Unlabeled Resources - {bad_rcs}"


@pytest.fixture(scope="module")
def check_components(network_addons_config):
    """
    Check that all CNAO components are accounted for.
    If a new cnao component is added, the test needs to be modified.
    It's name should be added to EXPECTED_CNAO_COMP and EXPECTED_CNAO_COMP_NAMES.
    """
    bad_components = []
    for component in network_addons_config.instance.spec.keys():
        if component == "selfSignConfiguration":
            continue
        if component not in EXPECTED_CNAO_COMP:
            bad_components.append(component)
    if bad_components:
        raise UnaccountedComponents(components=bad_components)


@pytest.fixture(scope="module")
def net_add_op_bridge_device(utility_pods, worker_node1):
    with utilities.network.network_device(
        interface_type=utilities.network.LINUX_BRIDGE,
        nncp_name="test-network-operator",
        interface_name="br1test",
        network_utility_pods=utility_pods,
        node_selector=worker_node1.name,
    ) as br_dev:
        yield br_dev


@pytest.fixture(scope="module")
def net_add_op_br1test_nad(namespace, net_add_op_bridge_device):
    with utilities.network.network_nad(
        nad_type=utilities.network.LINUX_BRIDGE,
        nad_name=net_add_op_bridge_device.bridge_name,
        interface_name=net_add_op_bridge_device.bridge_name,
        namespace=namespace,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def net_add_op_bridge_attached_vm(namespace, net_add_op_br1test_nad):
    name = "oper-test-vm"
    with VirtualMachineForTests(
        namespace=namespace.name,
        interfaces=[net_add_op_br1test_nad.name],
        networks={net_add_op_br1test_nad.name: net_add_op_br1test_nad.name},
        name=name,
        body=fedora_vm_body(name=name),
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.mark.post_upgrade
@pytest.mark.polarion("CNV-2520")
def test_component_installed_by_operator(network_addons_config):
    """
    Verify that the network addons operator is supposed to install Linux-Bridge
    (a mandatory default component), by checking if the component appears in
    the operator CR.
    """
    component_name_in_cr = "linuxBridge"
    assert (
        component_name_in_cr in network_addons_config.instance.spec.keys()
    ), f"{component_name_in_cr} is missing from the network operator CR."


@pytest.mark.post_upgrade
@pytest.mark.polarion("CNV-2296")
def test_linux_bridge_functionality(net_add_op_bridge_attached_vm):
    """
    Verify the linux-bridge component valid functionality.
    Start a VM and verify it starts successfully, as an indication of successful
    deployment of linux-bridge.
    """
    net_add_op_bridge_attached_vm.vmi.wait_until_running()


@pytest.mark.polarion("CNV-6754")
def test_cnao_labels(
    admin_client,
    network_addons_config,
    check_components,
    hco_namespace,
    is_post_cnv_upgrade_cluster,
):
    """
    Verify that all cnao components are labeled accordingly, first checking there are no unaccounted components,
    then checking each component's resources.
    """
    verify_cnao_labels(
        admin_client=admin_client,
        namespace=hco_namespace.name,
        network_addons_config=network_addons_config,
        is_post_cnv_upgrade_cluster=is_post_cnv_upgrade_cluster,
    )
