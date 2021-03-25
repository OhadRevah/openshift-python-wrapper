import logging
import os
import re
from multiprocessing import Process

import dictdiffer
import yaml
from ocp_resources.catalog_source import CatalogSource
from ocp_resources.cluster_version import ClusterVersion
from ocp_resources.datavolume import DataVolume
from ocp_resources.deployment import Deployment
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.image_content_source_policy import ImageContentSourcePolicy
from ocp_resources.machine_config_pool import MachineConfigPool
from ocp_resources.package_manifest import PackageManifest
from ocp_resources.pod import Pod
from ocp_resources.resource import Resource, ResourceEditor
from ocp_resources.subscription import Subscription
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from ocp_resources.virtual_machine import VirtualMachineInstanceMigration
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
from utilities.virt import run_command, wait_for_vm_interfaces


APP_REGISTRY = "rh-osbs-operators"
LOGGER = logging.getLogger(__name__)


def wait_for_dvs_import_completed(dvs_list):
    def _dvs_import_completed():
        return all(map(lambda dv: dv.status == DataVolume.Status.SUCCEEDED, dvs_list))

    LOGGER.info("Wait for DVs import to end.")
    samples = TimeoutSampler(
        wait_timeout=1200,
        sleep=10,
        func=_dvs_import_completed,
    )
    for sample in samples:
        if sample:
            return


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


def wait_for_vms_interfaces(vms_list):
    for vm in vms_list:
        wait_for_vm_interfaces(vmi=vm.vmi, timeout=1100)


def migrate_vm_and_validate(vm, when):
    vmi_node_before_migration = vm.vmi.instance.status.nodeName
    with VirtualMachineInstanceMigration(
        name=f"{when}-upgrade-migration", namespace=vm.namespace, vmi=vm.vmi
    ) as mig:
        mig.wait_for_status(status=mig.Status.SUCCEEDED, timeout=720)
        assert vm.vmi.instance.status.nodeName != vmi_node_before_migration
        assert vm.vmi.instance.status.migrationState.completed


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


def pod_status_and_image(
    dyn_client,
    hco_namespace,
    operators_version,
    old_operators_pods,
    delete_pod=False,
):
    """
    Wait for a new operator pod to be created.
    If delete_pod - new operator pods will be deleted (test operator
    resiliency)
    """

    oper_name, image_ver = operators_version
    LOGGER.info(f"Verify operator pod {oper_name} replacement.")

    old_operators_pods = [pod for pod in old_operators_pods if oper_name in pod.name]

    def _get_new_operator_pod():
        if old_operators_pods:
            return wait_for_operator_replacement(
                dyn_client=dyn_client,
                hco_namespace=hco_namespace,
                operator_name=oper_name,
                old_operator_pods=old_operators_pods,
            )
        # For new operators which did not exist in a previous version
        else:
            return get_operator_by_name(
                dyn_client=dyn_client,
                hco_namespace=hco_namespace,
                operator_name=oper_name,
            )

    new_operator_pod = _get_new_operator_pod()

    def _check_operator_pod_image():
        nonlocal new_operator_pod
        if not new_operator_pod.exists:
            new_operator_pod = _get_new_operator_pod()
        return new_operator_pod.instance.spec.containers[0].image == image_ver

    LOGGER.info(
        f"Wait for {new_operator_pod.name} to get updated image version {image_ver}"
    )
    image_sampler = TimeoutSampler(
        wait_timeout=utilities.constants.TIMEOUT_30MIN,
        sleep=1,
        func=_check_operator_pod_image,
    )

    for image_sample in image_sampler:
        if image_sample:
            break

    if delete_pod:
        new_operator_pod.delete(wait=True, force=True)
        # Operator pod is deleted, fetching a new pod
        new_operator_pod = get_operator_by_name(
            dyn_client=dyn_client,
            hco_namespace=hco_namespace,
            operator_name=oper_name,
        )

    LOGGER.info(f"Wait for {new_operator_pod.name} to be ready")
    new_operator_pod.wait_for_condition(
        condition=Pod.Condition.READY,
        status=Pod.Condition.Status.TRUE,
        timeout=utilities.constants.TIMEOUT_30MIN,
    )


def check_pods_status_and_images(
    dyn_client, hco_namespace, old_operators_pods, operators_versions, delete_pods
):
    LOGGER.info(
        "Check that all operators PODs have been replaced and have new images version and have status ready. "
        "Testing upgrade resilience is "
        f"{'enabled (pods will be deleted during upgrade)' if delete_pods else 'disabled'}."
    )

    processes = []

    for operators_version in operators_versions.items():
        sub_process = Process(
            name=operators_version[0],
            target=pod_status_and_image,
            kwargs={
                "dyn_client": dyn_client,
                "hco_namespace": hco_namespace,
                "operators_version": operators_version,
                "old_operators_pods": old_operators_pods,
                "delete_pod": delete_pods,
            },
        )
        processes.append(sub_process)
        sub_process.start()

    for process in processes:
        process.join()

    failed_processes = {
        process.name: process.exitcode for process in processes if process.exitcode != 0
    }
    assert (
        not failed_processes
    ), f"Failed to replace all operator pods. Failed pods: {failed_processes}"


def get_operators_names_and_images(csv):
    operators_versions = {}
    for deploy in csv.instance.spec.install.spec.deployments:
        operators_versions[deploy.name] = deploy.spec.template.spec.containers[0].image
    return operators_versions


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


def upgrade_path(cnv_upgrade_dict):
    current_version = re.search(
        r"([0-9]+)\.([0-9]+)\.([0-9]+)", cnv_upgrade_dict["current_version"]
    )

    target_version, target_channel = utils.cnv_target_version_channel(
        cnv_version=cnv_upgrade_dict["target_version"]
    )

    if current_version.group(1) < target_version.group(1):
        return "x-stream", target_channel
    elif current_version.group(2) < target_version.group(2):
        return "y-stream", target_channel
    elif current_version.group(3) < target_version.group(3):
        return "z-stream", target_channel


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


def check_tier2_pods_images(dyn_client, hco_namespace, hco_target_version):
    updated_images_list = get_images_from_manifest(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace,
        target_version=hco_target_version,
    )
    cluster_pods = get_cluster_pods(
        dyn_client=dyn_client, hco_namespace=hco_namespace, pods_type="tier-2"
    )

    unreplaced_pods = [
        pod.name
        for pod in cluster_pods
        if pod.instance.spec.containers[0].image not in updated_images_list
    ]

    assert (
        not unreplaced_pods
    ), f"The following pods images were not replaced: {unreplaced_pods}"


def get_hyperconverged_cr(dyn_client, namespace):
    for cr in HyperConverged.get(dyn_client=dyn_client, namespace=namespace):
        return cr


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
    def _delta_add_openstack_topology_zone_nova(delta):
        verb, path, patch = delta
        if verb != "add":
            return False
        if path[1:] != ["labels"]:
            return False
        if patch != [("topology.cinder.csi.openstack.org/zone", "nova")]:
            return False
        return True

    acceptable_deltas = [_delta_add_openstack_topology_zone_nova]

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
            if not any(func(delta) for func in acceptable_deltas):
                return False

        # if nothing has indicated the nodes status is not verified then they are verified
        return True

    nodes_status_after_upgrade = None
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
        nodes_delta = stringify_dict_delta_for_logging(
            first=nodes_status_after_upgrade, second=nodes_status_before_upgrade
        )
        LOGGER.error(
            f"Nodes before upgrade: {nodes_status_before_upgrade}."
            f"\nNodes after upgrade: {nodes_status_after_upgrade}."
            f"\nNodes delta: {nodes_delta}."
        )
        raise


def stringify_dict_delta_for_logging(first, second):
    # for easier debugging it is easier to see the delta between dicts
    return "\n".join(
        map(
            str,
            dictdiffer.diff(
                first=second,
                second=first,
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
    """will delete the ICSP if it exists, else it will do nothing"""
    for icsp in ImageContentSourcePolicy.get(dyn_client=admin_client, name="iib"):
        icsp.delete(wait=True)


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


def get_mcp(dyn_client):
    return list(MachineConfigPool.get(dyn_client=dyn_client))


def wait_for_mcp_update(dyn_client):
    def _get_mcp_condition(condition_type):
        return [
            condition
            for mcp in mcp_list
            for condition in mcp.instance.status.conditions
            if condition["type"] == condition_type
        ]

    def _wait_for_condition_status(condition_type, timeout):
        # The list of exceptions is needed because during mcp update;
        # the nodes are updated and the connection may be interrupted.
        # TODO: change exceptions to use this PR once it is merged
        #  https://gitlab.cee.redhat.com/cnv-qe/ocp-python-wrapper/-/merge_requests/147
        samples = TimeoutSampler(
            wait_timeout=timeout,
            sleep=5,
            func=_get_mcp_condition,
            condition_type=condition_type,
            exceptions=(
                NewConnectionError,
                ConnectionRefusedError,
                ProtocolError,
                ResponseError,
                MaxRetryError,
            ),
        )

        for sample in samples:
            if all(
                [
                    True if condition["status"] == "True" else False
                    for condition in sample
                ]
            ):
                break

    mcp_list = get_mcp(dyn_client=dyn_client)
    LOGGER.info("Wait for mcp update to start.")
    _wait_for_condition_status(
        condition_type=MachineConfigPool.Status.UPDATING,
        timeout=utilities.constants.TIMEOUT_15MIN,
    )

    LOGGER.info("Wait for mcp update to end.")
    _wait_for_condition_status(
        condition_type=MachineConfigPool.Status.UPDATED,
        timeout=utilities.constants.TIMEOUT_75MIN,
    )


def upgrade_cnv(
    dyn_client,
    hco_namespace,
    hco_version,
    image,
    cnv_upgrade_path,
    upgrade_resilience,
    cnv_subscription_source,
    cnv_source,
):
    LOGGER.info(f"CNV upgrade: {cnv_upgrade_path}")
    LOGGER.info("Get all operators PODs before upgrade")
    old_operators_pods = get_cluster_pods(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace.name,
        pods_type="operator",
    )
    all_old_pods = get_cluster_pods(
        dyn_client=dyn_client, hco_namespace=hco_namespace.name, pods_type="all"
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

    LOGGER.info("Get the install plan.")
    install_plan = utils.wait_for_install_plan(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace.name,
        hco_target_version=hco_version,
    )

    LOGGER.info("Approve the install plan to trigger the upgrade.")
    utils.approve_install_plan(install_plan=install_plan)

    LOGGER.info("Wait for a new CSV")
    new_csv = utils.wait_for_csv(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace.name,
        hco_target_version=hco_version,
    )

    LOGGER.info("Check that CSV status is Installing")
    new_csv.wait_for_status(
        status=new_csv.Status.INSTALLING,
        timeout=utilities.constants.TIMEOUT_10MIN,
        stop_status=None,
    )

    LOGGER.info("Get all operators PODs names and images version from the new CSV")
    operators_versions = get_operators_names_and_images(csv=new_csv)

    LOGGER.info("Wait for operators replacement.")
    check_pods_status_and_images(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace.name,
        old_operators_pods=old_operators_pods,
        operators_versions=operators_versions,
        delete_pods=upgrade_resilience,
    )

    LOGGER.info("Wait for HCO conditions after upgrade")
    wait_for_hco_conditions(admin_client=dyn_client)

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

    LOGGER.info("Wait for the new HCO to be available.")
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

    LOGGER.info("Wait for all previous pods to be deleted")
    wait_for_pods_removal(pods_list=all_old_pods)

    LOGGER.info("Verify tier-2 pods images were updated")
    check_tier2_pods_images(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace.name,
        hco_target_version=hco_version,
    )


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
        exceptions=(
            # TODO: these exceptions should be handled as part of the ocp_resources package.
            #   These exceptions are to be ignored on API calls when upgrading OCP/CNV or any machine config changes.
            #   until it is introduced to ocp_resources package they should be handled here.
            NotFoundError,
            ResourceNotFoundError,
            InternalServerError,
            NewConnectionError,
            ConnectionRefusedError,
            ProtocolError,
            ResponseError,
            MaxRetryError,
        ),
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
