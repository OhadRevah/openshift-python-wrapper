import logging

import pytest
from ocp_resources.package_manifest import PackageManifest
from openshift.dynamic.exceptions import NotFoundError
from pytest_testconfig import config as py_config


LOGGER = logging.getLogger(__name__)


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
def kubevirt_package_manifest_channel(kubevirt_package_manifest, cnv_current_version):
    """
    Return channel name from Kubevirt Package Manifest.
    """
    for channel in kubevirt_package_manifest.status.channels:
        if channel.currentCSVDesc.version == cnv_current_version:
            LOGGER.info(
                f"Getting channel associated with cnv version: {cnv_current_version}"
            )
            return channel.name
    raise NotFoundError(
        (
            "Not able to find 'stable' channel in the package manifest."
            f"Avaliable channels: {kubevirt_package_manifest.status.channels}"
        )
    )


@pytest.fixture()
def skip_if_nightly_channel(kubevirt_package_manifest):
    for channel in kubevirt_package_manifest.status.channels:
        if "nightly" in channel.name:
            pytest.skip(
                f"Test skipping due to nightly build. Current channel is {channel.name}"
            )


@pytest.fixture()
def csv_annotation(csv_scope_session):
    """
    Gets csv annotation for csv_scope_session.ApiGroup.INFRA_FEATURES
    """
    return csv_scope_session.instance.metadata.annotations.get(
        f"{csv_scope_session.ApiGroup.OPERATORS_OPENSHIFT_IO}/infrastructure-features"
    )
