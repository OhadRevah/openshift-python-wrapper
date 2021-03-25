import re

from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.installplan import InstallPlan
from ocp_resources.utils import TimeoutSampler
from openshift.dynamic.exceptions import ConflictError

import utilities.constants


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
        wait_timeout=utilities.constants.TIMEOUT_10MIN,
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
        status=install_plan.Status.COMPLETE, timeout=utilities.constants.TIMEOUT_10MIN
    )


def wait_for_install_plan(dyn_client, hco_namespace, hco_target_version):
    samples = TimeoutSampler(
        wait_timeout=180,
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
