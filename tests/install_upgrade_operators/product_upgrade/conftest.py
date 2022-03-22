import logging
import re

import pytest
from ocp_resources.machine_config_pool import MachineConfigPool
from ocp_resources.operator_hub import OperatorHub
from ocp_resources.resource import ResourceEditor
from pytest_testconfig import py_config

import tests.install_upgrade_operators.product_upgrade.utils as upgrade_utils
from tests.install_upgrade_operators.utils import wait_for_csv
from utilities.infra import get_related_images_name_and_version


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def cnv_image_name(pytestconfig):
    cnv_image_url = pytestconfig.option.cnv_image
    if not cnv_image_url:
        return

    # Image name format example staging: registry-proxy-stage.engineering.redhat.com/rh-osbs-stage/iib:v4.5
    # Image name format example osbs: registry-proxy.engineering.redhat.com/rh-osbs/iib:45131
    try:
        return re.search(r"[/.*](\w+):", cnv_image_url).group(1)
    except IndexError:
        LOGGER.error(
            "Can not find CNV image name "
            "(example: registry-proxy.engineering.redhat.com/rh-osbs/iib:45131 should find 'iib')"
        )
        raise


@pytest.fixture()
def disabled_default_sources_in_operatorhub(
    admin_client, is_deployment_from_production_source
):
    if not is_deployment_from_production_source:
        for source in OperatorHub.get(dyn_client=admin_client):
            with ResourceEditor(
                patches={source: {"spec": {"disableAllDefaultSources": True}}}
            ) as edited_source:
                yield edited_source
    else:
        yield


@pytest.fixture(scope="module")
def nodes_taints_before_upgrade(nodes):
    return upgrade_utils.get_nodes_taints(nodes=nodes)


@pytest.fixture(scope="module")
def nodes_labels_before_upgrade(nodes):
    return upgrade_utils.get_nodes_labels(nodes=nodes)


@pytest.fixture()
def update_image_content_source(
    is_deployment_from_production_source,
    is_deployment_from_stage_source,
    pytestconfig,
    cnv_image_name,
    cnv_registry_source,
    admin_client,
    cnv_upgrade_path,
    tmpdir,
):
    if not cnv_upgrade_path or is_deployment_from_production_source:
        # not needed when upgrading OCP
        # Generate ICSP only in case of deploying from OSBS or Stage source; Production source does not require ICSP.
        return

    icsp_file_path = upgrade_utils.generate_icsp_file(
        tmpdir=tmpdir,
        cnv_index_image=pytestconfig.option.cnv_image,
        cnv_image_name=cnv_image_name,
        source_map=cnv_registry_source["source_map"],
    )

    if is_deployment_from_stage_source:
        upgrade_utils.update_icsp_stage_mirror(icsp_file_path=icsp_file_path)

    LOGGER.info("pausing MCP updates while modifying ICSP")
    with ResourceEditor(
        patches={
            mcp: {"spec": {"paused": True}}
            for mcp in MachineConfigPool.get(dyn_client=admin_client)
        }
    ):
        # delete the existing ICSP and then create the new one
        # apply is not good enough due to the amount of annotations we have
        # the amount of annotations we have is greater than the maximum size of a payload that is supported with apply
        LOGGER.info("Deleting existing ICSP.")
        upgrade_utils.delete_icsp(admin_client=admin_client)

        LOGGER.info("Creating new ICSP.")
        upgrade_utils.create_icsp_from_file(icsp_file_path=icsp_file_path)

    LOGGER.info("Wait for MCP to update now that we modified the ICSP")
    upgrade_utils.wait_for_mcp_update(dyn_client=admin_client)


@pytest.fixture(scope="session")
def pre_upgrade_operators_pods(admin_client, hco_namespace):
    LOGGER.info("Get all operators pods before upgrade")
    return upgrade_utils.get_cluster_pods(
        dyn_client=admin_client,
        hco_namespace=hco_namespace.name,
        pods_type="operator",
    )


@pytest.fixture(scope="session")
def all_pre_upgrade_pods(admin_client, hco_namespace):
    LOGGER.info("Get all CNV pods before upgrade")
    return upgrade_utils.get_cluster_pods(
        dyn_client=admin_client, hco_namespace=hco_namespace.name, pods_type="all"
    )


@pytest.fixture(scope="session")
def pre_upgrade_pods_images(all_pre_upgrade_pods):
    return {
        pod.name: pod.instance.spec.containers[0].image for pod in all_pre_upgrade_pods
    }


@pytest.fixture(scope="session")
def pre_upgrade_operators_versions(csv_scope_session):
    LOGGER.info("Get all operators Pods names and images version from the current CSV")
    return upgrade_utils.get_operators_names_and_info(csv=csv_scope_session)


@pytest.fixture(scope="session")
def pre_upgrade_related_images_name_and_versions(
    admin_client, hco_namespace, hco_current_version
):
    LOGGER.info("Get all related images names and versions from the current CSV")
    return get_related_images_name_and_version(
        dyn_client=admin_client,
        hco_namespace=hco_namespace.name,
        version=hco_current_version,
    )


@pytest.fixture(scope="session")
def updated_catalog_source_image(
    admin_client, is_deployment_from_production_source, pytestconfig
):
    if not is_deployment_from_production_source:
        LOGGER.info("Deployment is not from production; update catalog source image.")
        upgrade_utils.update_image_in_catalog_source(
            dyn_client=admin_client,
            namespace=py_config["marketplace_namespace"],
            image=pytestconfig.option.cnv_image,
        )


@pytest.fixture(scope="session")
def updated_subscription_channel_and_source(
    cnv_subscription_scope_session, cnv_registry_source
):
    LOGGER.info("Update subscription channel and source.")
    upgrade_utils.update_subscription_channel_and_source(
        cnv_subscription=cnv_subscription_scope_session,
        cnv_subscription_channel="stable",
        cnv_subscription_source=cnv_registry_source["cnv_subscription_source"],
    )


@pytest.fixture(scope="session")
def approved_upgrade_install_plan(admin_client, hco_namespace, hco_target_version):
    upgrade_utils.approve_upgrade_install_plan(
        dyn_client=admin_client,
        hco_namespace=hco_namespace.name,
        hco_target_version=hco_target_version,
    )


@pytest.fixture(scope="session")
def upgrade_target_csv(admin_client, hco_namespace, hco_target_version):
    LOGGER.info(f"Wait for a new CSV with version {hco_target_version}")
    return wait_for_csv(
        dyn_client=admin_client,
        hco_namespace=hco_namespace.name,
        hco_target_version=hco_target_version,
    )


@pytest.fixture(scope="session")
def target_related_images_name_and_versions(
    admin_client, hco_namespace, hco_target_version
):
    LOGGER.info("Get all related images names and versions from the new CSV")
    return get_related_images_name_and_version(
        dyn_client=admin_client,
        hco_namespace=hco_namespace.name,
        version=hco_target_version,
    )
