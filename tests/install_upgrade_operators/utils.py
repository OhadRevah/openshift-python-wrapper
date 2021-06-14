import re

from ocp_resources.cdi import CDI
from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.deployment import Deployment
from ocp_resources.installplan import InstallPlan
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.utils import TimeoutSampler
from openshift.dynamic.exceptions import ConflictError

from utilities.constants import TIMEOUT_3MIN, TIMEOUT_10MIN


def cnv_target_version_channel(cnv_version):
    target_version = re.search(r"([0-9]+)\.([0-9]+)\.([0-9]+)", cnv_version)
    target_channel = ".".join(target_version.group(1, 2))
    return target_version, target_channel


def get_new_csv(dyn_client, hco_namespace, hco_target_version):
    for csv in ClusterServiceVersion.get(
        dyn_client=dyn_client, namespace=hco_namespace
    ):
        if csv.name == hco_target_version:
            return csv


def wait_for_csv(dyn_client, hco_namespace, hco_target_version):
    csv_sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=1,
        func=get_new_csv,
        dyn_client=dyn_client,
        hco_namespace=hco_namespace,
        hco_target_version=hco_target_version,
    )
    for csv_sample in csv_sampler:
        if csv_sample:
            return csv_sample


def get_install_plan(dyn_client, hco_namespace, hco_target_version):
    for ip in InstallPlan.get(dyn_client=dyn_client, namespace=hco_namespace):
        if hco_target_version == ip.instance.spec.clusterServiceVersionNames[0]:
            return ip


def approve_install_plan(install_plan):
    ip_dict = install_plan.instance.to_dict()
    ip_dict["spec"]["approved"] = True
    install_plan.update(resource_dict=ip_dict)
    install_plan.wait_for_status(
        status=install_plan.Status.COMPLETE, timeout=TIMEOUT_10MIN
    )


def wait_for_install_plan(dyn_client, hco_namespace, hco_target_version):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_3MIN,
        sleep=1,
        func=get_install_plan,
        exceptions=ConflictError,  # need to ignore ConflictError during install plan reconciliation
        dyn_client=dyn_client,
        hco_namespace=hco_namespace,
        hco_target_version=hco_target_version,
    )
    for sample in samples:
        if sample:
            return sample


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
