import logging

import pytest
from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.package_manifest import PackageManifest
from openshift.dynamic.exceptions import NotFoundError
from pytest_testconfig import config as py_config


LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def csv(admin_client):
    for csv in ClusterServiceVersion.get(
        dyn_client=admin_client, namespace="openshift-cnv"
    ):
        return csv


@pytest.fixture()
def kubevirt_package_manifest(admin_client, hco_namespace):
    """
    Find kubevirt package manifest associated with hco-catalogsource.
    """
    package_manifest_name = py_config["hco_cr_name"]
    label_selector = "catalog=hco-catalogsource"
    for resource_field in PackageManifest.get(
        dyn_client=admin_client,
        namespace=py_config["marketplace_namespace"],
        label_selector=label_selector,
        raw=True,
    ):
        if resource_field.metadata.name == package_manifest_name:
            LOGGER.info(
                f"Found expected packagemanefest: {resource_field.metadata.name}: "
                f"in catalog: {resource_field.metadata.labels.catalog}"
            )
            return resource_field
    raise NotFoundError(
        f"Not able to find any packagemanifest {package_manifest_name} in {label_selector} source."
    )


@pytest.fixture()
def stable_channel_package_manifest(kubevirt_package_manifest, cnv_current_version):
    """
    Return 'stable' channel from Kubevirt Package Manifest.
    """
    kubevirt_version = kubevirt_package_manifest.status.channels[
        0
    ].currentCSVDesc.version
    LOGGER.info(
        f"Getting channels associated with kubevirt version: {kubevirt_version},"
        f"cnv version: {cnv_current_version}"
    )
    return [
        channel.name
        for channel in kubevirt_package_manifest.status.channels
        if kubevirt_version == cnv_current_version
    ]
