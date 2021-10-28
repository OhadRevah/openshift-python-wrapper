import inspect
import logging
import re

from benedict import benedict
from ocp_resources.cdi import CDI
from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.deployment import Deployment
from ocp_resources.installplan import InstallPlan
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.operator_condition import OperatorCondition
from ocp_resources.resource import ResourceEditor
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from openshift.dynamic.exceptions import ConflictError, NotFoundError

from utilities.constants import TIMEOUT_10MIN, TIMEOUT_20MIN, TIMEOUT_40MIN
from utilities.hco import wait_for_hco_conditions
from utilities.infra import (
    collect_logs,
    collect_resources_for_test,
    get_kubevirt_package_manifest,
    wait_for_consistent_resource_conditions,
)
from utilities.storage import DEFAULT_CDI_CONDITIONS
from utilities.virt import DEFAULT_KUBEVIRT_CONDITIONS


LOGGER = logging.getLogger(__name__)


def get_package_manifest_images(admin_client):
    package = get_kubevirt_package_manifest(admin_client=admin_client)
    for channel in package.status.channels:
        if channel.name == "stable":
            LOGGER.info("For kubevirt package manifest stable channel was found.")
            return channel.currentCSVDesc["relatedImages"]
    raise NotFoundError("For kubevirt package manifest, could not find stable channel")


def cnv_target_version_channel(cnv_version):
    target_version = re.search(r"([0-9]+)\.([0-9]+)\.([0-9]+)", cnv_version)
    target_channel = ".".join(target_version.group(1, 2))
    return target_version, target_channel


def wait_for_csv(dyn_client, hco_namespace, hco_target_version):
    csv_sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=1,
        func=ClusterServiceVersion.get,
        dyn_client=dyn_client,
        namespace=hco_namespace,
        hco_target_version=hco_target_version,
    )
    csvs = None
    try:
        for csvs in csv_sampler:
            for csv in csvs:
                if csv.name == hco_target_version:
                    return csv
    except TimeoutExpiredError:
        LOGGER.error(
            f"timeout waiting for target cluster service version: version={hco_target_version} csvs={csvs}"
        )
        if collect_logs():
            collect_resources_for_test(resources_to_collect=[ClusterServiceVersion])
        raise


def wait_for_operator_condition(dyn_client, hco_namespace, name, upgradable):
    LOGGER.info(f"Wait for the operator condition. Name:{name} Upgradable:{upgradable}")
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=1,
        func=OperatorCondition.get,
        dyn_client=dyn_client,
        namespace=hco_namespace,
        name=name,
    )
    sample = None
    try:
        for sample in samples:
            for operator_condition in sample:
                upgradeable_condition = next(
                    (
                        condition
                        for condition in operator_condition.instance.spec.conditions
                        if condition.type == "Upgradeable"
                    ),
                    None,
                )
                if (
                    upgradeable_condition is not None
                    and upgradeable_condition.status == str(upgradable)
                ):
                    return operator_condition
    except TimeoutExpiredError:
        LOGGER.error(
            f"timeout waiting for operator version: name={name}, upgradable:{upgradable}"
        )
        raise


def approve_install_plan(install_plan):
    ResourceEditor(patches={install_plan: {"spec": {"approved": True}}}).update()
    install_plan.wait_for_status(
        status=install_plan.Status.COMPLETE, timeout=TIMEOUT_20MIN
    )


def wait_for_install_plan(dyn_client, hco_namespace, hco_target_version):
    install_plan_sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_40MIN,
        sleep=1,
        func=InstallPlan.get,
        exceptions_dict={
            ConflictError: []
        },  # need to ignore ConflictError during install plan reconciliation
        dyn_client=dyn_client,
        hco_namespace=hco_namespace,
        hco_target_version=hco_target_version,
    )
    install_plan_samples = None
    try:
        for install_plan_samples in install_plan_sampler:
            for ip in install_plan_samples:
                if hco_target_version == ip.instance.spec.clusterServiceVersionNames[0]:
                    return ip
    except TimeoutExpiredError:
        LOGGER.error(
            f"timeout waiting for target install plan: version={hco_target_version} ips={install_plan_samples}"
        )
        if collect_logs():
            collect_resources_for_test(resources_to_collect=[InstallPlan])
        raise


def get_deployment_by_name(admin_client, namespace_name, deployment_name):
    """
    Gets a deployment object by name

    Args:
        admin_client (DynamicClient): a DynamicClient object
        namespace_name (str): name of the associated namespace
        deployment_name (str): Name of the deployment

    Returns:
        Deployment: Deployment object
    """
    for dp in Deployment.get(
        dyn_client=admin_client,
        namespace=namespace_name,
        name=deployment_name,
    ):
        return dp


def wait_for_stabilize(
    admin_client,
    hco_namespace,
    wait_timeout=TIMEOUT_10MIN,
    polling_interval=1,
    consecutive_checks_count=2,
    condition_key1="type",
    condition_key2="status",
):
    wait_for_hco_conditions(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        sleep=polling_interval,
        consecutive_checks_count=consecutive_checks_count,
    )
    wait_for_consistent_resource_conditions(
        dynamic_client=admin_client,
        hco_namespace=hco_namespace,
        expected_conditions=DEFAULT_KUBEVIRT_CONDITIONS,
        resource_kind=KubeVirt,
        condition_key1=condition_key1,
        condition_key2=condition_key2,
        total_timeout=wait_timeout,
        polling_interval=polling_interval,
        consecutive_checks_count=consecutive_checks_count,
    )
    wait_for_consistent_resource_conditions(
        dynamic_client=admin_client,
        hco_namespace=hco_namespace,
        expected_conditions=DEFAULT_CDI_CONDITIONS,
        resource_kind=CDI,
        condition_key1=condition_key1,
        condition_key2=condition_key2,
        total_timeout=wait_timeout,
        polling_interval=polling_interval,
        consecutive_checks_count=consecutive_checks_count,
    )


def get_network_addon_config(admin_client):
    """
    Gets NetworkAddonsConfig object

    Args:
        admin_client (DynamicClient): a DynamicClient object

    Returns:
        Generator of NetworkAddonsConfig: Generator of NetworkAddonsConfig
    """
    for nao in NetworkAddonsConfig.get(dyn_client=admin_client, name="cluster"):
        return nao


def wait_for_spec_change(expected, get_spec_func, base_path):
    """
    Waits for spec values to get propagated

    Args:
        expected (dict): dictionary of values that would be used to update hco cr
        get_spec_func (function): function to fetch current spec dictionary
        base_path (list): list of associated keys for a given kind
    """

    def _compare_spec_values():
        spec_dict = benedict(get_spec_func()).get(base_path)
        return (
            sorted(expected.items()) == sorted(spec_dict.items()),
            f"Compare mismatch: expected={expected} spec_dict={spec_dict}",
        )

    samplers = TimeoutSampler(
        wait_timeout=60,
        sleep=5,
        exceptions_dict={AssertionError: []},
        func=_compare_spec_values,
    )
    try:
        for compare_result in samplers:
            if _compare_spec_values:
                LOGGER.info(
                    f"{get_function_name(function_name=get_spec_func)}: Found expected spec values: '{expected}'"
                )
                return True

    except TimeoutExpiredError:
        LOGGER.error(
            f"{get_function_name(function_name=get_spec_func)}: Timed out waiting for CR with expected spec."
            f" spec: '{expected}' diff:'{compare_result}'"
        )
        raise


def get_function_name(function_name):
    """
    Return the text of the source code for a function

    Args:
        function_name (function object): function object

    Returns:
        str: name of the function
    """
    return inspect.getsource(function_name).split("(")[0].split(" ")[-1]
