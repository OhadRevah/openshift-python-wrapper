import logging
import os
import re
from multiprocessing import Process

import dictdiffer
import yaml
from ocp_resources.catalog_source import CatalogSource
from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.cluster_version import ClusterVersion
from ocp_resources.datavolume import DataVolume
from ocp_resources.deployment import Deployment
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.image_content_source_policy import ImageContentSourcePolicy
from ocp_resources.machine_config_pool import MachineConfigPool
from ocp_resources.node import Node
from ocp_resources.package_manifest import PackageManifest
from ocp_resources.pod import Pod
from ocp_resources.resource import Resource, ResourceEditor
from ocp_resources.subscription import Subscription
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from openshift.dynamic.exceptions import (
    InternalServerError,
    NotFoundError,
    ResourceNotFoundError,
)
from pytest_testconfig import py_config
from urllib3.exceptions import (
    MaxRetryError,
    NewConnectionError,
    ProtocolError,
    ResponseError,
)

import utilities.constants
from tests.install_upgrade_operators import utils
from utilities.hco import wait_for_hco_conditions
from utilities.infra import (
    collect_logs,
    collect_resources_for_test,
    write_to_extras_file,
)
from utilities.virt import run_command


LOGGER = logging.getLogger(__name__)
BASE_EXCEPTIONS_DICT = {
    NewConnectionError: [],
    ConnectionRefusedError: [],
    ProtocolError: [],
    ResponseError: [],
    MaxRetryError: [],
    InternalServerError: [],
}


def wait_for_dvs_import_completed(dvs_list):
    def _dvs_import_completed():
        return all(map(lambda dv: dv.status == DataVolume.Status.SUCCEEDED, dvs_list))

    LOGGER.info("Wait for DVs import to end.")
    samples = TimeoutSampler(
        wait_timeout=utilities.constants.TIMEOUT_60MIN,
        sleep=10,
        func=_dvs_import_completed,
    )
    try:
        for sample in samples:
            if sample:
                return
    except TimeoutExpiredError:
        dv_status = {dv.name: dv.status for dv in dvs_list}
        LOGGER.error(f"dvs were not imported within timeout: status={dv_status}")
        raise


def wait_for_pods_removal(pods_list):
    def _get_remaining_existing_pods():
        return [(pod.name, pod.status) for pod in pods_list if pod.exists]

    LOGGER.info("Wait for pods to be removed.")
    samples = TimeoutSampler(
        wait_timeout=utilities.constants.TIMEOUT_10MIN,
        sleep=10,
        func=_get_remaining_existing_pods,
    )
    sample = None  # will be set each iteration, setting it here allows referencing it during exception handling
    try:
        for sample in samples:
            if not sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Some old pods were not deleted: {sample}")
        raise


def assert_bridge_and_vms_on_same_node(vm_a, vm_b, bridge):
    for vm in [vm_a, vm_b]:
        assert vm.vmi.node.name == bridge.node_selector


def assert_node_is_marked_by_bridge(bridge_nad, vm):
    for bridge_annotation in bridge_nad.instance.metadata.annotations.values():
        assert bridge_annotation in vm.vmi.node.instance.status.capacity.keys()
        assert bridge_annotation in vm.vmi.node.instance.status.allocatable.keys()


def wait_for_operator_replacement(
    dyn_client, hco_namespace, operator_name, old_operator_pods
):
    old_operator_pod_names = [pod.name for pod in old_operator_pods]
    operator_sampler = TimeoutSampler(
        wait_timeout=utilities.constants.TIMEOUT_10MIN,
        sleep=1,
        func=get_operator_by_name,
        dyn_client=dyn_client,
        hco_namespace=hco_namespace,
        operator_name=operator_name,
    )

    for operator in operator_sampler:
        if operator.name not in old_operator_pod_names:
            LOGGER.debug(
                f"Old operator: {old_operator_pod_names} new operator: {operator.name}"
            )
            return operator


def wait_for_new_operator_pod(
    dyn_client,
    hco_namespace,
    operator_name,
    operator_target_info,
    old_operators_pods,
    delete_pod=False,
):
    """
    Wait for a new operator pod to be created.
    If delete_pod - new operator pods will be deleted (test operator
    resiliency)
    """

    def _get_new_operator_pod():
        if old_operators_pods:
            return wait_for_operator_replacement(
                dyn_client=dyn_client,
                hco_namespace=hco_namespace,
                operator_name=operator_name,
                old_operator_pods=old_operators_pods,
            )
        # For new operators which did not exist in a previous version
        else:
            return get_operator_by_name(
                dyn_client=dyn_client,
                hco_namespace=hco_namespace,
                operator_name=operator_name,
            )

    def _check_operator_pod_image(pod):
        try:
            return (
                pod.instance.spec.containers[0].image == operator_target_info["image"]
            )
        except NotFoundError:
            return False

    old_operators_pods = [
        pod for pod in old_operators_pods if operator_name in pod.name
    ]

    LOGGER.info(
        f"Verify new operator pod {operator_name} {'replacement' if old_operators_pods else ''}."
    )

    new_pod_sampler = TimeoutSampler(
        wait_timeout=utilities.constants.TIMEOUT_30MIN,
        sleep=1,
        func=_get_new_operator_pod,
    )

    new_operator_pod = None
    for new_operator_pod in new_pod_sampler:
        if (
            operator_target_info["strategy"] != "Recreate"
            and not is_pod_in_ready_condition(pod=new_operator_pod)
            and old_operators_pods
        ):
            old_pods_in_ready_condition = {
                pod.name: is_pod_in_ready_condition(pod=pod)
                for pod in old_operators_pods
            }
            assert all(old_pods_in_ready_condition.values()), (
                f"Old pods removed before new pods are ready, "
                f"new_pod={new_operator_pod.name} old_pods_ready={old_pods_in_ready_condition}"
            )
        if _check_operator_pod_image(pod=new_operator_pod):
            break

    if delete_pod:
        new_operator_pod.delete(wait=True, timeout=utilities.constants.TIMEOUT_10MIN)
        # Operator pod is deleted, fetching a new pod
        new_operator_pod = get_operator_by_name(
            dyn_client=dyn_client,
            hco_namespace=hco_namespace,
            operator_name=operator_name,
        )

    LOGGER.info(f"Wait for {new_operator_pod.name} to be ready")
    new_operator_pod.wait_for_condition(
        condition=Pod.Condition.READY,
        status=Pod.Condition.Status.TRUE,
        timeout=utilities.constants.TIMEOUT_30MIN,
    )


def is_pod_in_ready_condition(pod):
    try:
        conditions = pod.instance.status.conditions
    except NotFoundError:
        return False
    else:
        for condition in conditions:
            if (
                condition.type == Pod.Condition.READY
                and condition.status == Pod.Condition.Status.TRUE
            ):
                return True
    return False


def wait_for_operator_pod_replacements(
    dyn_client,
    hco_namespace,
    old_operators_pods,
    operators_current_versions,
    operators_target_versions,
    delete_pods,
):
    LOGGER.info(
        "Verify all operators Pods with new images get replaced and have the new images version and status ready. "
        "Testing upgrade resilience is "
        f"{'enabled (pods will be deleted during upgrade)' if delete_pods else 'disabled'}."
    )

    processes = []

    for operator_name, operator_target_info in operators_target_versions.items():
        operator_current_info = operators_current_versions.get(operator_name)
        if (
            operator_current_info
            and operator_target_info["image"] != operator_current_info["image"]
        ):
            sub_process = Process(
                name=operator_name,
                target=wait_for_new_operator_pod,
                kwargs={
                    "dyn_client": dyn_client,
                    "hco_namespace": hco_namespace,
                    "operator_name": operator_name,
                    "operator_target_info": operator_target_info,
                    "old_operators_pods": old_operators_pods,
                    "delete_pod": delete_pods,
                },
            )
            processes.append(sub_process)
            sub_process.start()
        else:
            LOGGER.info(f"operator pod {operator_name} does not need replacement.")

    for process in processes:
        process.join()

    failed_processes = {
        process.name: process.exitcode for process in processes if process.exitcode != 0
    }
    assert (
        not failed_processes
    ), f"Failures during operator pods replacement. Failed processes={failed_processes}"


def get_related_images_name_and_version(dyn_client, hco_namespace, version):
    related_images_name_and_versions = {}
    csv = utils.get_current_csv(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace,
        hco_current_version=version,
    )
    for item in csv.instance.spec.relatedImages:
        # example of "name": 'registry.redhat.io/container-native-virtualization/node-maintenance-operator:v2.6.3-1'
        # sample output after parsing: name = 'node-maintenance-operator' and version = 'v2.6.3-1'
        name, version = item["name"].rpartition("/")[-1].split(":", 1)
        related_images_name_and_versions[name] = {
            "image": item["image"],
            "version": version,
        }
    return related_images_name_and_versions


def get_operators_names_and_info(csv):
    operators_info = {}
    for deploy in csv.instance.spec.install.spec.deployments:
        operators_info[deploy.name] = {
            "image": deploy.spec.template.spec.containers[0].image,
            "strategy": deploy.spec.strategy.get("type", "RollingUpdate"),
        }
    return operators_info


def get_clusterversion(dyn_client):
    for cvo in ClusterVersion.get(dyn_client=dyn_client):
        return cvo


def update_clusterversion_channel(dyn_client, ocp_channel):
    cvo = get_clusterversion(dyn_client=dyn_client)
    LOGGER.info(f"patching cluster to use new OCP channel {ocp_channel}")
    ResourceEditor(patches={cvo: {"spec": {"channel": ocp_channel}}}).update()
    cvo.wait_for_condition(
        condition=cvo.Condition.AVAILABLE, timeout=utilities.constants.TIMEOUT_15MIN
    )


def get_clusterversion_state_version_conditions(dyn_client):
    cvo = get_clusterversion(dyn_client=dyn_client)
    return (
        cvo.instance.status.history[0].state,
        cvo.instance.status.history[0].version,
        cvo.instance.status.conditions,
    )


def update_image_in_catalog_source(dyn_client, namespace, image):
    assert image, "no image supplied"
    #  The cnv_image cli argument can be None in the case of production/staging version.
    #  Since the user doesn't need to specify a custom IIB image.
    #  This is just here in case somehow this would run it should fail here.
    #  Otherwise an empty string would be set for the image.
    #  This would screw up the cluster and likely be hard to find the source of the issue.
    LOGGER.info(f"Change hco-catalogsource image: image={image}")
    for catalog_source in CatalogSource.get(
        dyn_client=dyn_client, namespace=namespace, name="hco-catalogsource"
    ):
        ResourceEditor(patches={catalog_source: {"spec": {"image": image}}}).update()


def update_subscription_channel_and_source(
    dyn_client, hco_namespace, cnv_subscription_channel, cnv_subscription_source
):
    LOGGER.info(
        f"Change subscription channel and source: channel={cnv_subscription_channel} source={cnv_subscription_source}"
    )
    for subscription in Subscription.get(
        dyn_client=dyn_client,
        namespace=hco_namespace,
        name="hco-operatorhub",
    ):
        ResourceEditor(
            {
                subscription: {
                    "spec": {
                        "channel": cnv_subscription_channel,
                        "source": cnv_subscription_source,
                    }
                }
            }
        ).update()


def get_cluster_pods(dyn_client, hco_namespace, pods_type):
    """
    Returns a list of cluster pods:
    pods_type - operator/tier-2 (non-operator) /all
    """
    pods = list(Pod.get(dyn_client=dyn_client, namespace=hco_namespace))
    cluster_pods = []
    for pod in pods:
        # Operator pods
        if pods_type == "operator" and "operator" in pod.name:
            cluster_pods.append(pod)
        # Tier-2 pods (created by operators)
        elif pods_type == "tier-2" and "operator" not in pod.name:
            cluster_pods.append(pod)
        # All pods
        elif pods_type == "all":
            cluster_pods.append(pod)

    assert cluster_pods
    return cluster_pods


def get_operator_by_name(dyn_client, hco_namespace, operator_name):
    pods = list(Pod.get(dyn_client=dyn_client, namespace=hco_namespace))
    operator_pod = list(filter(lambda x: operator_name in x.name, pods))[0]
    return operator_pod


def get_images_from_manifest(dyn_client, hco_namespace, target_version):
    for package in PackageManifest.get(dyn_client=dyn_client, namespace=hco_namespace):
        if package.name == py_config["hco_cr_name"]:
            return [
                channel.currentCSVDesc.relatedImages
                for channel in package.instance.status.channels
                if channel.currentCSV == target_version
            ][0]


def check_tier2_pods_images(
    dyn_client,
    hco_namespace,
    target_related_images_name_and_versions,
    pods_not_to_be_removed,
):
    """
    Checks the tier2 CNV pods images to make sure all current pods after upgrade are using target images

    Using the related images from the csv after the upgrade and getting a list of currently running cluster pods
    Exclude the pods which are not to be removed and check that remaining pods images are expected

    Args:
        dyn_client (:obj:`DynamicClient`): admin client or unprivileged client
        hco_namespace (:obj:`Namespace`): the namespace to use for getting the pod resources
        target_related_images_name_and_versions (dict): related images names and versions from post-upgrade csv
        pods_not_to_be_removed (list): list of pods not to be removed (images that don't need replacing)
    """
    target_images_list = [
        item["image"] for item in target_related_images_name_and_versions.values()
    ]
    pods_not_to_be_replaced_names = [pod.name for pod in pods_not_to_be_removed]
    current_tier2_cluster_pods = get_cluster_pods(
        dyn_client=dyn_client, hco_namespace=hco_namespace, pods_type="tier-2"
    )
    cluster_pods_to_be_replaced = filter(
        lambda pod: pod.name not in pods_not_to_be_replaced_names,
        current_tier2_cluster_pods,
    )

    unreplaced_pods = [
        pod.name
        for pod in cluster_pods_to_be_replaced
        if pod.instance.spec.containers[0].image not in target_images_list
    ]

    assert (
        not unreplaced_pods
    ), f"The following pods images were not replaced: {unreplaced_pods}"


def get_nodes_status(nodes):
    nodes_dict = {}
    for node in nodes:
        node_conditions = [
            {condition.type: condition.status}
            for condition in node.instance.status.conditions
        ]
        nodes_dict[node.name] = {
            "labels": node.instance.metadata.labels,
            "taints": node.instance.spec.taints,
            "unschedulable": node.instance.unschedulable,
            "conditions": node_conditions,
        }

    return nodes_dict


def cleanup_node_status(node_status):
    # converts the node_status objects into a string to be able to load it back into a dictionary
    return dict(yaml.load(str(node_status)))


def verify_nodes_status_after_upgrade(nodes, nodes_status_before_upgrade):
    """
    Verifies the nodes by checking their status before and after the upgrade.
    a nodes status is comprised of; labels, taints, conditions, and if they are unschedulable

    For taints, conditions, and unschedulable status the nodes are compared directly between before and after
    For labels there are some considerations as the labels can be modified
        by node-labeller (kubernetes features) and/or by the underlying infrastructure (PSI)

    Args:
        nodes (list): Nodes in the cluster
        nodes_status_before_upgrade (dict): status of the Nodes in the cluster before the upgrade
    """

    def _delta_add_openstack_topology_zone_nova(verb, path, patch):
        return (
            verb == "add"
            and path[1:] == ["labels"]
            and patch == [("topology.cinder.csi.openstack.org/zone", "nova")]
        )

    def _delta_remove_kubernetes_feature_labels(verb, path, patch):
        return (
            verb == "remove"
            and path[1:] == ["labels"]
            and all(
                label_name.startswith("feature.node.kubernetes.io/")
                for label_name, label_value in patch
            )
        )

    def _delta_add_kubevirt_feature_labels(verb, path, patch):
        return (
            verb == "add"
            and path[1:] == ["labels"]
            and all(
                label_name.startswith(
                    (
                        "hyperv.node.kubevirt.io/",
                        "cpu-model.node.kubevirt.io/",
                        "cpu-feature.node.kubevirt.io/",
                    )
                )
                for label_name, label_value in patch
            )
        )

    def _verify_status(before, after):
        # some deltas are acceptable, so those must be allowed.
        # using dictdiffer.diff to find the delta between before and after dictionaries of nodes
        # then checking each diff in a list of functions which can take a diff and approve it
        # if any of those functions approve the diff then this diff is acceptable
        # if any delta is not approved by at least one acceptable function then the nodes status is not verified
        for delta in dictdiffer.diff(
            first=cleanup_node_status(node_status=before),
            second=cleanup_node_status(node_status=after),
            dot_notation=False,
        ):
            verb, path, patch = delta
            if not any(func(verb, path, patch) for func in acceptable_deltas):
                return False

        # if nothing has indicated the nodes status is not verified then they are verified
        return True

    acceptable_deltas = [
        _delta_add_openstack_topology_zone_nova,
        _delta_remove_kubernetes_feature_labels,
        _delta_add_kubevirt_feature_labels,
    ]
    nodes_status_after_upgrade = {}
    nodes_sampler = TimeoutSampler(
        wait_timeout=utilities.constants.TIMEOUT_10MIN,
        sleep=5,
        func=get_nodes_status,
        nodes=nodes,
    )

    try:
        for nodes_status_after_upgrade in nodes_sampler:
            if _verify_status(
                before=nodes_status_before_upgrade, after=nodes_status_after_upgrade
            ):
                return

    except TimeoutExpiredError:
        LOGGER.error("Nodes did not match after timeout, attempting to produce delta.")
        if collect_logs():
            collect_resources_for_test(resources_to_collect=[Node])
            for name, data in [
                ("nodes_status_before_upgrade.yaml", nodes_status_before_upgrade),
                ("nodes_status_after_upgrade.yaml", nodes_status_after_upgrade),
            ]:
                write_to_extras_file(
                    extras_file_name=name,
                    content=yaml.dump(cleanup_node_status(node_status=data)),
                )
        try:
            nodes_delta = stringify_dict_delta_for_logging(
                first=cleanup_node_status(node_status=nodes_status_before_upgrade),
                second=cleanup_node_status(node_status=nodes_status_after_upgrade),
            )
        except TypeError as exc:
            # sometimes there is a NoneType error when creating the delta of the dictionaries,
            # it should be ignored so that before/after dictionaries can still be logged.
            nodes_delta = f"<ErrorObtainingDelta({exc})>"
        else:
            if collect_logs():
                write_to_extras_file(
                    extras_file_name="nodes_delta.txt", content=nodes_delta
                )
        LOGGER.error(f"Nodes delta:\n{nodes_delta}.")
        raise


def stringify_dict_delta_for_logging(first, second):
    # for easier debugging it is easier to see the delta between dicts
    return "\n".join(
        map(
            str,
            dictdiffer.diff(
                first=first,
                second=second,
                dot_notation=False,
            ),
        )
    )


def verify_cnv_pods_are_running(dyn_client, hco_namespace):
    def _get_pods_that_are_not_running():
        return [
            pod
            for pod in get_cluster_pods(
                dyn_client=dyn_client, hco_namespace=hco_namespace.name, pods_type="all"
            )
            if pod.status != Pod.Status.RUNNING
        ]

    samples = TimeoutSampler(
        wait_timeout=utilities.constants.TIMEOUT_10MIN,
        sleep=10,
        func=_get_pods_that_are_not_running,
    )
    sample = None
    try:
        for sample in samples:
            if not sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Some pods are not running: {sample}.")
        raise


def delete_icsp(admin_client):
    """
    Deletes the ImageContentSourcePolicy from the cluster

    Ignores NotFoundError

    Args:
        admin_client (DynamicClient): Open connection to remote cluster
    """
    try:
        for icsp in ImageContentSourcePolicy.get(dyn_client=admin_client):
            LOGGER.info(f"Deleting ImageContentSourcePolicy {icsp.name}")
            icsp.delete(wait=True)
    except NotFoundError:
        pass


def generate_icsp_file(tmpdir, cnv_index_image, cnv_image_name, source_map):
    icsp_file_name = "imageContentSourcePolicy.yaml"
    LOGGER.info(f"Create catalog mirror file {icsp_file_name} (ICSP)")
    output_directory = os.path.join(tmpdir, f"{cnv_image_name}-manifests")
    rc, out, err = run_command(
        command=[
            "oc",
            "adm",
            "catalog",
            "mirror",
            cnv_index_image,
            source_map,
            "--manifests-only",
            "--to-manifests",
            output_directory,
        ],
        verify_stderr=False,
    )
    assert rc, f"Command to generate catalog mirror failed. out={out}"

    icsp_file_path = os.path.join(output_directory, icsp_file_name)
    assert os.path.isfile(
        icsp_file_path
    ), f"ICSP file does not exist in path {icsp_file_path}"

    return icsp_file_path


def create_icsp_from_file(icsp_file_path):
    rc, out, err = run_command(
        command=["oc", "create", "-f", icsp_file_path], verify_stderr=False
    )
    assert rc, f"Failed to create ICSP policy {icsp_file_path}"


def update_icsp_stage_mirror(icsp_file_path):
    # TODO: Remove once mirror catalog from stage is fixed
    rc, out, err = run_command(
        command=[
            "sed",
            "-i",
            "-e",
            "s|/container-native-virtualization-\\(.*\\)|/\\1|g",
            icsp_file_path,
        ]
    )
    assert rc, f"Failed to update stage mirror in ICSP {icsp_file_path}"


def wait_for_mcp_update(dyn_client):
    def _get_all_mcp_conditions():
        return {
            mcp.name: mcp.instance.status.conditions
            for mcp in MachineConfigPool.get(dyn_client=dyn_client)
        }

    def _are_all_mcp_matching_condition(mcp_conditions, condition_type):
        return all(
            [
                condition["status"] == "True"
                for conditions in mcp_conditions.values()
                for condition in conditions
                if condition["type"] == condition_type
            ]
        )

    def _wait_for_condition_status(condition_type, timeout):
        # The list of exceptions is needed because during mcp update;
        # the nodes are updated and the connection may be interrupted.
        LOGGER.info(
            f"mcp wait for condition: desired={condition_type} current={_get_all_mcp_conditions()}"
        )
        mcp_conditions_sampler = TimeoutSampler(
            wait_timeout=timeout,
            sleep=5,
            func=_get_all_mcp_conditions,
            exceptions_dict=BASE_EXCEPTIONS_DICT,
        )
        mcp_conditions = {}
        try:
            for mcp_conditions in mcp_conditions_sampler:
                if _are_all_mcp_matching_condition(
                    mcp_conditions=mcp_conditions,
                    condition_type=condition_type,
                ):
                    break
        except TimeoutExpiredError:
            LOGGER.error(
                f"mcp not at desired condition before timeout: desired={condition_type} current={mcp_conditions}"
            )
            if collect_logs():
                write_to_extras_file(
                    extras_file_name="mcp_conditions.yaml",
                    content=yaml.dump(
                        {
                            key: list(map(dict, conditions))
                            for key, conditions in mcp_conditions.items()
                        }
                    ),
                )
                collect_resources_for_test(resources_to_collect=[MachineConfigPool])
            raise

    LOGGER.info("Wait for mcp update to start.")
    try:
        _wait_for_condition_status(
            condition_type=MachineConfigPool.Status.UPDATING,
            timeout=utilities.constants.TIMEOUT_15MIN,
        )
    except TimeoutExpiredError:
        if _are_all_mcp_matching_condition(
            mcp_conditions=_get_all_mcp_conditions(),
            condition_type=MachineConfigPool.Status.UPDATED,
        ):
            # This can happen if the MCP transitions quickly and the UPDATING status is missed
            LOGGER.info(
                f"ignoring timeout since mcp is already in final desired condition: {MachineConfigPool.Status.UPDATED}"
            )
        else:
            raise

    LOGGER.info("Wait for mcp update to end.")
    _wait_for_condition_status(
        condition_type=MachineConfigPool.Status.UPDATED,
        timeout=utilities.constants.TIMEOUT_75MIN,
    )


def upgrade_cnv(
    dyn_client,
    hco_namespace,
    hco_target_version,
    hco_current_version,
    image,
    cnv_upgrade_path,
    upgrade_resilience,
    cnv_subscription_source,
    cnv_source,
):
    LOGGER.info(f"CNV upgrade: {cnv_upgrade_path}")
    LOGGER.info("Get all operators Pods before upgrade")
    old_operators_pods = get_cluster_pods(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace.name,
        pods_type="operator",
    )
    all_old_pods = get_cluster_pods(
        dyn_client=dyn_client, hco_namespace=hco_namespace.name, pods_type="all"
    )
    # retrieve the old pod images now because after the upgrade the pod will raise an exception:
    # kubernetes.client.exceptions.ApiException: (404)
    # Reason: NotFound
    old_pod_images = {
        pod.name: pod.instance.spec.containers[0].image for pod in all_old_pods
    }

    LOGGER.info(f"Get current CSV {hco_current_version}")
    current_csv = utils.get_current_csv(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace.name,
        hco_current_version=hco_current_version,
    )

    LOGGER.info("Get all operators Pods names and images version from the current CSV")
    operators_current_versions = get_operators_names_and_info(csv=current_csv)

    LOGGER.info("Get all related images names and versions from the current CSV")
    current_related_images_name_and_versions = get_related_images_name_and_version(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace.name,
        version=hco_current_version,
    )

    if cnv_source != "production":
        LOGGER.info("Update catalog source image.")
        update_image_in_catalog_source(
            dyn_client=dyn_client,
            namespace=py_config["marketplace_namespace"],
            image=image,
        )

    LOGGER.info("Update subscription channel and source.")
    update_subscription_channel_and_source(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace.name,
        cnv_subscription_channel="stable",
        cnv_subscription_source=cnv_subscription_source,
    )

    approve_upgrade_install_plan(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace.name,
        hco_target_version=hco_target_version,
    )

    LOGGER.info(f"Wait for a new CSV with version {hco_target_version}")
    new_csv = utils.wait_for_csv(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace.name,
        hco_target_version=hco_target_version,
    )
    LOGGER.info("Get all related images names and versions from the new CSV")
    target_related_images_name_and_versions = get_related_images_name_and_version(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace.name,
        version=hco_target_version,
    )

    LOGGER.info("Check that CSV status is Installing")
    try:
        new_csv.wait_for_status(
            status=new_csv.Status.INSTALLING,
            timeout=utilities.constants.TIMEOUT_10MIN,
            stop_status=None,
        )
    except TimeoutExpiredError:
        # in the case of no change there will be no/short "installing" time, and we shouldn't fail on it
        if not new_csv.instance.status.phase == ClusterServiceVersion.Status.SUCCEEDED:
            LOGGER.error(f"CSV status {new_csv.instance.status.phase}")
            raise

    LOGGER.info("determine which old pods should be gone after upgrade")
    pods_to_be_removed, pods_not_to_be_removed = determine_pods_to_be_removed(
        all_old_pods=all_old_pods,
        old_pod_images=old_pod_images,
        current_related_images_name_and_versions=current_related_images_name_and_versions,
        target_related_images_name_and_versions=target_related_images_name_and_versions,
    )
    check_images_during_upgrade = True
    if set(
        item["image"] for item in current_related_images_name_and_versions.values()
    ) == set(
        item["image"] for item in target_related_images_name_and_versions.values()
    ):
        LOGGER.info("Image contents are the same")
        check_images_during_upgrade = False

    if check_images_during_upgrade:
        LOGGER.info("Get all operators Pods names and images version from the new CSV")
        operators_target_versions = get_operators_names_and_info(csv=new_csv)

        LOGGER.info("Wait for operators replacement.")
        wait_for_operator_pod_replacements(
            dyn_client=dyn_client,
            hco_namespace=hco_namespace.name,
            old_operators_pods=old_operators_pods,
            operators_current_versions=operators_current_versions,
            operators_target_versions=operators_target_versions,
            delete_pods=upgrade_resilience,
        )

    LOGGER.info("Wait for HCO conditions after upgrade")
    wait_for_hco_conditions(
        admin_client=dyn_client,
        hco_namespace=hco_namespace,
        wait_timeout=utilities.constants.TIMEOUT_20MIN,
    )

    LOGGER.info("Wait for HCO operator to be ready")
    hco_operator_pod = get_operator_by_name(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace.name,
        operator_name="hco-operator",
    )
    hco_operator_pod.wait_for_condition(
        condition=Pod.Condition.READY,
        status=Pod.Condition.Status.TRUE,
        timeout=utilities.constants.TIMEOUT_10MIN,
    )

    LOGGER.info("Wait for number of replicas = number of updated replicas")
    for deploy in Deployment.get(dyn_client, namespace=hco_namespace.name):
        deploy.wait_for_replicas(timeout=utilities.constants.TIMEOUT_10MIN)

    LOGGER.info("Wait for the HCO to be available.")
    for hco in HyperConverged.get(dyn_client=dyn_client, namespace=hco_namespace.name):
        hco.wait_for_condition(
            condition=Pod.Condition.AVAILABLE,
            status=Pod.Condition.Status.TRUE,
            timeout=utilities.constants.TIMEOUT_20MIN,
        )

    LOGGER.info("Check that CSV status is Succeeded")
    new_csv.wait_for_status(
        status=new_csv.Status.SUCCEEDED,
        timeout=utilities.constants.TIMEOUT_10MIN,
        stop_status=None,
    )

    if check_images_during_upgrade:
        LOGGER.info("Wait for all old pods to be removed after upgrade")
        wait_for_pods_removal(pods_list=pods_to_be_removed)

    LOGGER.info("Verify tier-2 pods images are as expected")
    check_tier2_pods_images(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace.name,
        target_related_images_name_and_versions=target_related_images_name_and_versions,
        pods_not_to_be_removed=pods_not_to_be_removed,
    )


def determine_pods_to_be_removed(
    all_old_pods,
    old_pod_images,
    current_related_images_name_and_versions,
    target_related_images_name_and_versions,
):
    """
    Filter the list of pods before the upgrade to determine which ones need to be replaced

    using the related images from the csv before and after the upgrade
    the image on pre-upgrade pod can be used to find the name of the related image on the pre-upgrade csv
    this can be matched to the related image on the post-upgrade csv using the name
    if the images are the same for that pod then it should not be removed by the upgrade

    Args:
        all_old_pods (list): list of all the pre-upgrade Pods
        old_pod_images (dict): the pre-upgrade Pod names mapped to their images
        current_related_images_name_and_versions (dict): related images names and versions from pre-upgrade csv
        target_related_images_name_and_versions (dict): related images names and versions from post-upgrade csv

    Returns:
        (list, list): (Pods to be removed, Pods not to be removed)

    Raises:
        (ValueError): pod images which are not found in related images
    """
    pods_to_be_removed = []
    pods_not_to_be_removed = []
    missing_pod_images = {}
    for pod in all_old_pods:
        pod_image = old_pod_images[pod.name]
        for image_name in current_related_images_name_and_versions.keys():
            if (
                current_related_images_name_and_versions[image_name]["image"]
                == pod_image
            ):
                break
        else:
            missing_pod_images[pod.name] = pod_image
            continue
        if (
            image_name not in target_related_images_name_and_versions
            or current_related_images_name_and_versions[image_name]["image"]
            != target_related_images_name_and_versions[image_name]["image"]
        ):
            pods_to_be_removed.append(pod)
        else:
            pods_not_to_be_removed.append(pod)
    if missing_pod_images:
        raise ValueError(
            f"some pod images not found in related images: {missing_pod_images}"
        )
    LOGGER.info(
        f"finished determining which pods should be removed: "
        f"to_remove={[pod.name for pod in pods_to_be_removed]} "
        f"not_to_remove={[pod.name for pod in pods_not_to_be_removed]}"
    )
    return pods_to_be_removed, pods_not_to_be_removed


def approve_upgrade_install_plan(dyn_client, hco_namespace, hco_target_version):
    LOGGER.info("Get the upgrade install plan.")
    install_plan = utils.wait_for_install_plan(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace,
        hco_target_version=hco_target_version,
    )

    LOGGER.info("Approve the upgrade install plan to trigger the upgrade.")
    utils.approve_install_plan(install_plan=install_plan)


def extract_ocp_version(ocp_image):
    # Extract the OCP version from the OCP URL input.
    ocp_version = re.search(r":(\d+\.\d+\.\d+)-(rc\.\d+)?", ocp_image)
    assert (
        ocp_version
    ), f"Cannot extract OCP version. OCP image url: {ocp_image} is invalid"
    return "-".join(filter(None, ocp_version.groups()))


def extract_clusterversion_version(clusterversion_version):
    # Extract the OCP version from the clusterversion version.
    ocp_version = re.search(r"(\d+\.\d+\.\d+)-?(rc\.\d+)?", clusterversion_version)
    assert (
        ocp_version
    ), f"Cannot extract OCP version. clusterversion version: {clusterversion_version} is invalid"
    return "-".join(filter(None, ocp_version.groups()))


def wait_until_ocp_upgrade_complete(ocp_image, dyn_client):
    LOGGER.info("Wait for OCP upgrade to complete")

    upgrade_conditions = {
        "Available": Resource.Condition.Status.TRUE,
        "Failing": Resource.Condition.Status.FALSE,
        "Progressing": Resource.Condition.Status.FALSE,
    }
    ocp_version = extract_ocp_version(ocp_image=ocp_image)

    samples = TimeoutSampler(
        wait_timeout=utilities.constants.TIMEOUT_180MIN,
        sleep=30,
        func=get_clusterversion_state_version_conditions,
        exceptions_dict={
            **BASE_EXCEPTIONS_DICT,
            NotFoundError: [],
            ResourceNotFoundError: [],
        },
        dyn_client=dyn_client,
    )

    sample = None  # will be set each iteration, setting it here allows referencing it during exception handling

    try:
        for sample in samples:
            if sample:
                state, version, actual_conditions = sample

                # TODO: if the ocp_channel is being used and --force is not, fail fast on VersionNotFound?
                # (condition.type == "RetrievedUpdates" and condition.reason == "VersionNotFound")

                actual_upgrade_conditions = {
                    condition.type: condition.status
                    for condition in actual_conditions
                    if condition.type in upgrade_conditions.keys()
                }

                if (
                    actual_upgrade_conditions == upgrade_conditions
                    and extract_clusterversion_version(version) == ocp_version
                    and state == "Completed"
                ):
                    return

    except TimeoutExpiredError:
        LOGGER.error(
            f"Timeout reached while upgrading OCP. "
            f"Expected (Completed, {ocp_version}, {upgrade_conditions}). "
            f"Actual: (state, version, conditions): {sample}"
        )
        raise


def upgrade_ocp(ocp_image, dyn_client, ocp_channel):
    if ocp_channel:
        # if the user is setting a channel then we modify the channel in the current cluster.
        # otherwise the channel is whatever is already set in the cluster.
        # NOTE: the command used below uses "force=true" so the channel is not necessarily required
        # but this behaviour may change in the future. And is mostly relevant when switching between prod/stage/osbs
        update_clusterversion_channel(dyn_client=dyn_client, ocp_channel=ocp_channel)

    LOGGER.info(f"Executing OCP upgrade command to image {ocp_image}")
    rc, out, err = run_command(
        command=[
            "oc",
            "adm",
            "upgrade",
            "--force=true",  # TODO: if the ocp_channel is being set then --force may not be required
            "--allow-explicit-upgrade",
            "--allow-upgrade-with-warnings",
            "--to-image",
            ocp_image,
        ],
        verify_stderr=False,
    )
    assert rc, f"OCP upgrade command failed. out: {out}. err: {err}"

    wait_until_ocp_upgrade_complete(ocp_image=ocp_image, dyn_client=dyn_client)
