import logging
import re

import pytest
from ocp_resources.machine_config_pool import MachineConfigPool
from ocp_resources.operator_hub import OperatorHub
from ocp_resources.resource import ResourceEditor
from pytest_testconfig import py_config

import tests.install_upgrade_operators.product_upgrade.utils as upgrade_utils
from tests.install_upgrade_operators.utils import wait_for_csv
from utilities.infra import get_related_images_name_and_version, run_command


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def cnv_image_name(pytestconfig):
    cnv_image_url = pytestconfig.option.cnv_image
    if not cnv_image_url:
        return

    # Image name format example staging: registry-proxy-stage.engineering.redhat.com/rh-osbs-stage/iib-pub-pending:v4.9
    # Image name format example osbs: registry-proxy.engineering.redhat.com/rh-osbs/iib:45131
    match = re.match(".*/(.*):", cnv_image_url)
    assert match, (
        f"Can not find CNV image name from: {cnv_image_url} "
        f"(example: registry-proxy.engineering.redhat.com/rh-osbs/iib:45131 should find 'iib')"
    )
    return match.group(1)


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
    master_mcp,
    worker_mcp,
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
    upgrade_utils.wait_for_machine_config_pool_updating_condition(
        machine_config_pools_list=[master_mcp, worker_mcp]
    )
    upgrade_utils.wait_for_machine_config_pool_updated_condition(
        machine_config_pools_list=[master_mcp, worker_mcp]
    )


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


@pytest.fixture(scope="session")
def ocp_image_url(pytestconfig):
    return pytestconfig.option.ocp_image


@pytest.fixture()
def triggered_ocp_upgrade(ocp_image_url):
    LOGGER.info(f"Executing OCP upgrade command to image {ocp_image_url}")
    rc, out, err = run_command(
        command=[
            "oc",
            "adm",
            "upgrade",
            "--force=true",
            "--allow-explicit-upgrade",
            "--allow-upgrade-with-warnings",
            "--to-image",
            ocp_image_url,
        ],
        verify_stderr=False,
    )
    assert rc, f"OCP upgrade command failed. out: {out}. err: {err}"


@pytest.fixture(scope="session")
def extracted_ocp_version_from_image_url(ocp_image_url):
    """
    Extract the OCP version from the OCP URL input.

    Expected inputs / output examples:
        quay.io/openshift-release-dev/ocp-release:4.10.9-x86_64 -> 4.10.9
        quay.io/openshift-release-dev/ocp-release:4.10.0-rc.6-x86_64 -> 4.10.0-rc.6
        registry.ci.openshift.org/ocp/release:4.11.0-0.nightly-2022-04-01-172551 -> 4.11.0-0.nightly-2022-04-01-172551
        registry.ci.openshift.org/ocp/release:4.11.0-0.ci-2022-04-06-165430 -> 4.11.0-0.ci-2022-04-06-165430
    """
    ocp_version_match = re.search(r"release:(.*?)(?:-x86_64$|$)", ocp_image_url)
    ocp_version = ocp_version_match.group(1) if ocp_version_match else None
    assert (
        ocp_version
    ), f"Cannot extract OCP version. OCP image url: {ocp_image_url} is invalid"
    LOGGER.info(f"OCP version {ocp_version} extracted from ocp image: {ocp_version}")
    return ocp_version


@pytest.fixture(scope="session")
def master_mcp():
    return upgrade_utils.get_machine_config_pool_by_name(mcp_name="master")


@pytest.fixture(scope="session")
def worker_mcp():
    return upgrade_utils.get_machine_config_pool_by_name(mcp_name="worker")


@pytest.fixture()
def started_machine_config_pool_update(master_mcp, worker_mcp):
    upgrade_utils.wait_for_machine_config_pool_updating_condition(
        machine_config_pools_list=[master_mcp, worker_mcp]
    )
