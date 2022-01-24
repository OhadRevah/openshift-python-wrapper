import logging
from contextlib import contextmanager

import pytest
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.resource import ResourceEditor
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from openshift.dynamic.exceptions import NotFoundError
from pytest_testconfig import py_config

from tests.compute.ssp.supported_os.common_templates.golden_images.update_boot_source.constants import (
    CUSTOM_DATA_IMPORT_CRON_NAME,
    CUSTOM_DATA_SOURCE_NAME,
    DATA_SOURCE_READY_FOR_CONSUMPTION_MESSAGE,
    DEFAULT_FEDORA_REGISTRY_URL,
)
from tests.compute.ssp.supported_os.common_templates.golden_images.update_boot_source.utils import (
    wait_for_condition_message_value,
)
from tests.compute.ssp.utils import get_parameters_from_template
from utilities.constants import (
    DATA_SOURCE_NAME,
    TIMEOUT_5MIN,
    TIMEOUT_10MIN,
    TIMEOUT_20MIN,
    Images,
)
from utilities.exceptions import ResourceValueError
from utilities.infra import BUG_STATUS_CLOSED
from utilities.storage import get_images_server_url


LOGGER = logging.getLogger(__name__)

TESTS_AUTO_UPDATE_BOOT_SOURCE_NAME = [*py_config["auto_update_boot_sources_matrix"][0]][
    0
]
DUMMY_PVC_NAME = "dummy"
DATA_VOLUME_NOT_FOUND_ERROR = "DataVolume not found"
DATA_SOURCE_MANAGED_BY_CDI_LABEL = (
    f"{DataSource.ApiGroup.CDI_KUBEVIRT_IO}/dataImportCron"
)

pytestmark = pytest.mark.post_upgrade


def dv_for_data_source(name, data_source, admin_client):
    with DataVolume(
        client=admin_client,
        name=name,
        namespace=data_source.namespace,
        # underlying OS is not relevant
        url=f"{get_images_server_url(schema='http')}{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
        source="http",
        size=Images.Cirros.DEFAULT_DV_SIZE,
        storage_class=py_config["default_storage_class"],
        bind_immediate_annotation=True,
        api_name="storage",
    ) as dv:
        dv.wait_for_status(status=dv.Status.SUCCEEDED, timeout=TIMEOUT_20MIN)
        wait_for_condition_message_value(
            resource=data_source,
            expected_message=DATA_SOURCE_READY_FOR_CONSUMPTION_MESSAGE,
        )
        yield dv


def opt_in_status_str(opt_in):
    return f"opt-{'in' if opt_in else 'out'}"


def wait_for_data_source_reconciliation_after_update(data_source, opt_in):
    LOGGER.info(
        f"{opt_in_status_str(opt_in=opt_in)}: "
        f"Verify DataSource {data_source.name} is reconciled after update."
    )
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_10MIN,
            sleep=5,
            func=lambda: data_source.instance.spec.source.pvc.name != DUMMY_PVC_NAME,
        ):
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"dataSource {data_source.name} was not reconciled")
        raise


def wait_for_data_source_unchanged_referenced_pvc(data_source, pvc_name):
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_10MIN,
            sleep=5,
            func=lambda: data_source.instance.spec.source.pvc.name != pvc_name,
        ):
            if sample:
                raise ResourceValueError(
                    f"dataSource {data_source.name} PVC reference was updated, "
                    f"expected {pvc_name}, "
                    f"spec: {data_source.instance.spec}"
                )
    except TimeoutExpiredError:
        return


def wait_for_data_source_updated_referenced_pvc(data_source, pvc_name):
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_10MIN,
            sleep=5,
            func=lambda: data_source.instance.spec.source.pvc.name == pvc_name,
        ):
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"dataSource {data_source.name} PVC reference was not updated, "
            f"expected {pvc_name}, "
            f"spec: {data_source.instance.spec}"
        )
        raise


def delete_data_source_and_wait_for_reconciliation(golden_images_data_sources, opt_in):
    data_source = golden_images_data_sources[0]
    LOGGER.info(
        f"{opt_in_status_str(opt_in=opt_in)}: Verify DataSource {data_source.name} is reconciled after deletion."
    )

    data_source_orig_uid = data_source.instance.metadata.uid
    # Not passing 'wait' as creation time is almost instant
    data_source.delete()

    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_5MIN,
            sleep=5,
            func=lambda: data_source.instance.metadata.uid != data_source_orig_uid,
        ):
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error("DataSource was not reconciled after deletion")
        raise


def assert_missing_data_sources(
    opt_in, data_sources_names_from_templates, golden_images_data_sources
):
    LOGGER.info(
        f"{opt_in_status_str(opt_in=opt_in)}: Verify all expected DataSources from templates "
        f"{[data_source.name for data_source in golden_images_data_sources]} are created."
    )
    missing_data_sources = [
        data_source_ref
        for data_source_ref in data_sources_names_from_templates
        if data_source_ref
        not in [data_source.name for data_source in golden_images_data_sources]
    ]
    assert (
        not missing_data_sources
    ), f"Not all dataSources are created, missing: {missing_data_sources}"


@contextmanager
def update_data_source(data_source):
    with ResourceEditor(
        patches={
            data_source: {
                "spec": {
                    "source": {
                        "pvc": {
                            "name": DUMMY_PVC_NAME,
                            "namespace": data_source.namespace,
                        }
                    }
                }
            }
        }
    ):
        yield data_source


@pytest.fixture()
def golden_images_data_sources(admin_client, golden_images_namespace):
    return list(
        DataSource.get(dyn_client=admin_client, namespace=golden_images_namespace.name)
    )


@pytest.fixture()
def data_import_cron_managed_data_sources(golden_images_data_sources):
    return [
        data_source
        for data_source in golden_images_data_sources
        if DATA_SOURCE_MANAGED_BY_CDI_LABEL in data_source.labels.keys()
    ]


@pytest.fixture()
def data_sources_names_from_templates(base_templates):
    return set(
        [
            get_parameters_from_template(
                template=template, parameter_subset=DATA_SOURCE_NAME
            )[DATA_SOURCE_NAME]
            for template in base_templates
        ]
    )


@pytest.fixture()
def data_source_by_name(request, admin_client, golden_images_namespace):
    return DataSource(name=request.param, namespace=golden_images_namespace.name)


@pytest.fixture()
def data_source_referenced_pvc(data_source_by_name):
    return data_source_by_name.instance.spec.source.pvc.name


@pytest.fixture()
def opted_in_data_source(data_source_by_name):
    data_source_labels = data_source_by_name.instance.to_dict()["metadata"]["labels"]
    data_source_labels[DATA_SOURCE_MANAGED_BY_CDI_LABEL] = "true"
    with ResourceEditor(
        patches={data_source_by_name: {"metadata": {"labels": data_source_labels}}}
    ):
        yield


@pytest.fixture()
def uploaded_dv_for_dangling_data_source(admin_client, data_source_by_name):
    expected_pvc_name = data_source_by_name.instance.spec.source.pvc.name
    LOGGER.info(
        f"Create DV {expected_pvc_name} for dataSource {data_source_by_name.name}"
    )
    yield from dv_for_data_source(
        name=expected_pvc_name,
        data_source=data_source_by_name,
        admin_client=admin_client,
    )


@pytest.fixture()
def created_dv_for_data_import_cron_managed_data_source(
    admin_client, golden_images_namespace, data_source_by_name
):
    yield from dv_for_data_source(
        name=data_source_by_name.instance.spec.source.pvc.name,
        data_source=data_source_by_name,
        admin_client=admin_client,
    )


@pytest.fixture()
def updated_opted_in_data_source(data_import_cron_managed_data_sources):
    with update_data_source(
        data_source=data_import_cron_managed_data_sources[0]
    ) as data_source:
        yield data_source


@pytest.fixture()
def updated_opted_out_data_source(golden_images_data_sources):
    with update_data_source(data_source=golden_images_data_sources[0]) as data_source:
        yield data_source


@pytest.mark.polarion("CNV-7578")
def test_opt_in_all_referenced_data_sources_in_templates_exist(
    data_sources_names_from_templates,
    golden_images_data_sources,
):
    assert_missing_data_sources(
        opt_in=True,
        data_sources_names_from_templates=data_sources_names_from_templates,
        golden_images_data_sources=golden_images_data_sources,
    )


@pytest.mark.polarion("CNV-8234")
def test_opt_out_all_referenced_data_sources_in_templates_exist(
    disabled_common_boot_image_import_feature_gate,
    data_sources_names_from_templates,
    golden_images_data_sources,
):
    assert_missing_data_sources(
        opt_in=False,
        data_sources_names_from_templates=data_sources_names_from_templates,
        golden_images_data_sources=golden_images_data_sources,
    )


@pytest.mark.polarion("CNV-7667")
def test_opt_in_data_source_reconciles_after_deletion(golden_images_data_sources):
    delete_data_source_and_wait_for_reconciliation(
        golden_images_data_sources=golden_images_data_sources, opt_in=True
    )


@pytest.mark.bugzilla(
    2051105, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)
@pytest.mark.polarion("CNV-8030")
def test_opt_in_data_source_reconciles_after_update(updated_opted_in_data_source):
    wait_for_data_source_reconciliation_after_update(
        data_source=updated_opted_in_data_source, opt_in=True
    )


@pytest.mark.parametrize(
    "data_source_by_name, delete_dv, expected_condition_message",
    [
        pytest.param(
            "win2k19",
            False,
            DATA_SOURCE_READY_FOR_CONSUMPTION_MESSAGE,
            marks=(pytest.mark.polarion("CNV-7755")),
        ),
        pytest.param(
            "win2k19",
            True,
            DATA_VOLUME_NOT_FOUND_ERROR,
            marks=(pytest.mark.polarion("CNV-8099")),
        ),
    ],
    indirect=["data_source_by_name"],
)
def test_upload_dv_for_auto_update_dangling_data_sources(
    data_source_by_name,
    uploaded_dv_for_dangling_data_source,
    delete_dv,
    expected_condition_message,
):
    LOGGER.info("Verify DataSource condition is updated when referenced PVC is ready.")
    if delete_dv:
        uploaded_dv_for_dangling_data_source.delete(wait=True)
    wait_for_condition_message_value(
        resource=data_source_by_name,
        expected_message=expected_condition_message,
    )


@pytest.mark.polarion("CNV-7668")
def test_opt_out_data_source_reconciles_after_deletion(
    disabled_common_boot_image_import_feature_gate, golden_images_data_sources
):
    delete_data_source_and_wait_for_reconciliation(
        golden_images_data_sources=golden_images_data_sources, opt_in=False
    )


@pytest.mark.polarion("CNV-8095")
def test_opt_out_data_source_reconciles_after_update(
    disabled_common_boot_image_import_feature_gate, updated_opted_out_data_source
):
    wait_for_data_source_reconciliation_after_update(
        data_source=updated_opted_out_data_source, opt_in=False
    )


@pytest.mark.polarion("CNV-8100")
def test_opt_out_data_source_update(
    disabled_common_boot_image_import_feature_gate,
    golden_images_data_sources,
):
    LOGGER.info("Verify DataSources are updated to not reference auto-update DVs")
    for data_source in golden_images_data_sources:
        wait_for_condition_message_value(
            resource=data_source,
            expected_message=DATA_VOLUME_NOT_FOUND_ERROR,
        )


@pytest.mark.bugzilla(
    2044398, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)
@pytest.mark.parametrize(
    "data_source_by_name",
    [
        pytest.param(
            TESTS_AUTO_UPDATE_BOOT_SOURCE_NAME,
            marks=(pytest.mark.polarion("CNV-8029")),
        ),
    ],
    indirect=True,
)
def test_opt_in_label_data_source_when_pvc_exists(
    data_source_by_name,
    data_source_referenced_pvc,
    disabled_common_boot_image_import_feature_gate,
    created_dv_for_data_import_cron_managed_data_source,
    enabled_common_boot_image_import_feature_gate,
    opted_in_data_source,
):
    LOGGER.info(
        "Verify DataSource is managed by DataImportCron after labelled and a PVC exists."
    )
    wait_for_condition_message_value(
        resource=data_source_by_name,
        expected_message=DATA_SOURCE_READY_FOR_CONSUMPTION_MESSAGE,
    )
    wait_for_data_source_updated_referenced_pvc(
        data_source=data_source_by_name,
        pvc_name=data_source_referenced_pvc,
    )


@pytest.mark.parametrize(
    "updated_hco_with_custom_data_import_cron",
    [
        pytest.param(
            {
                "data_import_cron_name": CUSTOM_DATA_IMPORT_CRON_NAME,
                "data_import_cron_source_url": DEFAULT_FEDORA_REGISTRY_URL,
                "managed_data_source_name": CUSTOM_DATA_SOURCE_NAME,
            },
            marks=(pytest.mark.polarion("CNV-8048")),
        ),
    ],
    indirect=True,
)
def test_opt_out_custom_data_sources_not_deleted(
    admin_client,
    golden_images_namespace,
    updated_hco_with_custom_data_import_cron,
    disabled_common_boot_image_import_feature_gate,
):
    custom_data_source_name = updated_hco_with_custom_data_import_cron["spec"][
        "managedDataSource"
    ]
    LOGGER.info(
        f"Verify custom DataSource {custom_data_source_name} is not deleted after opt-out"
    )
    if not DataSource(
        client=admin_client,
        name=custom_data_source_name,
        namespace=golden_images_namespace.name,
    ).exists:
        raise NotFoundError(
            f"Custom DataSource {custom_data_source_name} not found after opt out"
        )


@pytest.mark.parametrize(
    "data_source_by_name",
    [
        pytest.param(
            TESTS_AUTO_UPDATE_BOOT_SOURCE_NAME,
            marks=(pytest.mark.polarion("CNV-7757")),
        ),
    ],
    indirect=True,
)
def test_data_source_with_existing_golden_image_pvc(
    disabled_common_boot_image_import_feature_gate,
    data_source_by_name,
    created_dv_for_data_import_cron_managed_data_source,
    enabled_common_boot_image_import_feature_gate,
):
    LOGGER.info(f"Verify DataSource {data_source_by_name.name} consumes an existing DV")
    wait_for_condition_message_value(
        resource=data_source_by_name,
        expected_message=DATA_SOURCE_READY_FOR_CONSUMPTION_MESSAGE,
    )

    LOGGER.info(
        "Verify DataSource reference is not updated if there's an existing PVC."
    )
    wait_for_data_source_unchanged_referenced_pvc(
        data_source=data_source_by_name,
        pvc_name=created_dv_for_data_import_cron_managed_data_source.name,
    )
