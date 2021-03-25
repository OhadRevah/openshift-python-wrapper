import logging
import re

from ocp_resources.cdi import CDI
from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.deployment import Deployment
from ocp_resources.installplan import InstallPlan
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.resource import ResourceEditor
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from openshift.dynamic.exceptions import ConflictError

from utilities.constants import TIMEOUT_10MIN, TIMEOUT_20MIN, TIMEOUT_40MIN
from utilities.infra import collect_resources_for_test


LOGGER = logging.getLogger(__name__)


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
        hco_namespace=hco_namespace,
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
        collect_resources_for_test(resources_to_collect=[ClusterServiceVersion])
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
        exceptions=ConflictError,  # need to ignore ConflictError during install plan reconciliation
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
        collect_resources_for_test(resources_to_collect=[InstallPlan])
        raise


def get_hyperconverged_kubevirt(admin_client, hco_namespace):
    for kv in KubeVirt.get(
        dyn_client=admin_client,
        namespace=hco_namespace.name,
        name="kubevirt-kubevirt-hyperconverged",
    ):
        return kv


def get_hyperconverged_cdi(admin_client, hco_namespace):
    for cdi in CDI.get(
        dyn_client=admin_client,
        namespace=hco_namespace.name,
        name="cdi-kubevirt-hyperconverged",
    ):
        return cdi


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
