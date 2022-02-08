import logging

import pytest
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.resource import ResourceEditor
from ocp_resources.utils import TimeoutSampler
from openshift.dynamic.exceptions import NotFoundError

from tests.compute.ssp.supported_os.common_templates.golden_images.update_boot_source.utils import (
    RESOURCE_MANAGED_BY_DATA_IMPORT_CRON_LABEL,
    enable_common_boot_image_import_feature_gate_wait_for_data_import_cron,
    generate_data_import_cron_dict,
    get_data_import_crons,
    update_common_boot_image_import_feature_gate,
    wait_for_deleted_data_import_crons,
)
from utilities.constants import (
    ENABLE_COMMON_BOOT_IMAGE_IMPORT_FEATURE_GATE,
    TIMEOUT_2MIN,
)


LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def enabled_common_boot_image_import_feature_gate(
    admin_client,
    hyperconverged_resource_scope_function,
    golden_images_namespace,
):
    enable_common_boot_image_import_feature_gate_wait_for_data_import_cron(
        hco_resource=hyperconverged_resource_scope_function,
        admin_client=admin_client,
        namespace=golden_images_namespace,
    )


@pytest.fixture()
def disabled_common_boot_image_import_feature_gate(
    admin_client,
    hyperconverged_resource_scope_function,
    golden_images_namespace,
    golden_images_data_import_crons,
):
    if hyperconverged_resource_scope_function.instance.spec.featureGates[
        ENABLE_COMMON_BOOT_IMAGE_IMPORT_FEATURE_GATE
    ]:
        update_common_boot_image_import_feature_gate(
            hco_resource=hyperconverged_resource_scope_function,
            enable_feature_gate=False,
        )
        wait_for_deleted_data_import_crons(
            data_import_crons=golden_images_data_import_crons
        )
        yield
        # Always enable enableCommonBootImageImport feature gate after test execution
        enable_common_boot_image_import_feature_gate_wait_for_data_import_cron(
            hco_resource=hyperconverged_resource_scope_function,
            admin_client=admin_client,
            namespace=golden_images_namespace,
        )
    else:
        yield


@pytest.fixture()
def golden_images_data_volumes(admin_client, golden_images_namespace):
    return list(
        DataVolume.get(
            dyn_client=admin_client,
            namespace=golden_images_namespace.name,
            label_selector=RESOURCE_MANAGED_BY_DATA_IMPORT_CRON_LABEL,
        )
    )


@pytest.fixture()
def golden_images_persistent_volume_claims(
    admin_client, golden_images_namespace, golden_images_data_volumes
):
    golden_image_pvcs = list(
        PersistentVolumeClaim.get(
            dyn_client=admin_client, namespace=golden_images_namespace.name
        )
    )
    return [
        pvc
        for pvc in golden_image_pvcs
        if pvc.name in [dv.name for dv in golden_images_data_volumes]
    ]


@pytest.fixture()
def updated_hco_with_custom_data_import_cron(
    request, hyperconverged_resource_scope_function
):
    data_import_cron_dict = generate_data_import_cron_dict(
        name=request.param["data_import_cron_name"],
        source_url=request.param["data_import_cron_source_url"],
        managed_data_source_name=request.param["managed_data_source_name"],
    )
    with ResourceEditor(
        patches={
            hyperconverged_resource_scope_function: {
                "spec": {"dataImportCronTemplates": [data_import_cron_dict]}
            }
        }
    ):
        yield data_import_cron_dict


@pytest.fixture()
def custom_data_import_cron(
    admin_client,
    golden_images_namespace,
    updated_hco_with_custom_data_import_cron,
):
    expected_data_import_cron_name = updated_hco_with_custom_data_import_cron[
        "metadata"
    ]["name"]
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=5,
        func=lambda: list(
            DataImportCron.get(
                dyn_client=admin_client,
                name=expected_data_import_cron_name,
                namespace=golden_images_namespace.name,
            )
        ),
        exceptions_dict={NotFoundError: []},
    ):
        if sample:
            return sample[0]


@pytest.fixture()
def custom_data_source(admin_client, custom_data_import_cron):
    custom_data_source_name = custom_data_import_cron.instance.spec.managedDataSource
    try:
        return list(
            DataSource.get(
                dyn_client=admin_client,
                name=custom_data_source_name,
                namespace=custom_data_import_cron.namespace,
            )
        )[0]
    except NotFoundError:
        LOGGER.error(
            f"DataSource {custom_data_source_name} is not found under {custom_data_import_cron.namespace} namespace."
        )
        raise


@pytest.fixture()
def golden_images_data_import_crons(admin_client, golden_images_namespace):
    return get_data_import_crons(
        admin_client=admin_client, namespace=golden_images_namespace
    )
