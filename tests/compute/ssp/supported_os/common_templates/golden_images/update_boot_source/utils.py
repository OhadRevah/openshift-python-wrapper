import logging
import re
from contextlib import contextmanager

from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.resource import NamespacedResource, ResourceEditor
from ocp_resources.template import Template
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from pytest_testconfig import py_config

from tests.compute.ssp.supported_os.common_templates.golden_images.update_boot_source.constants import (
    DATA_IMPORT_CRON_SUFFIX,
    DEFAULT_FEDORA_REGISTRY_URL,
)
from utilities.constants import (
    ENABLE_COMMON_BOOT_IMAGE_IMPORT_FEATURE_GATE,
    TIMEOUT_2MIN,
    TIMEOUT_5MIN,
)
from utilities.virt import VirtualMachineForTestsFromTemplate, running_vm


LOGGER = logging.getLogger(__name__)
RESOURCE_MANAGED_BY_DATA_IMPORT_CRON_LABEL = (
    f"{NamespacedResource.ApiGroup.CDI_KUBEVIRT_IO}/dataImportCron"
)


def wait_for_at_least_one_auto_update_data_import_cron(admin_client, namespace):
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_2MIN,
            sleep=5,
            func=get_data_import_crons,
            admin_client=admin_client,
            namespace=namespace,
        ):
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"No DataImportCrons found in {namespace.name}")
        raise


def get_data_import_crons(admin_client, namespace):
    return list(DataImportCron.get(dyn_client=admin_client, namespace=namespace.name))


def generate_data_import_cron_dict(
    name,
    source_url=None,
    managed_data_source_name=None,
):
    return {
        "metadata": {
            "name": name,
            "annotations": {"cdi.kubevirt.io/storage.bind.immediate.requested": "true"},
        },
        "spec": {
            "retentionPolicy": "None",
            "managedDataSource": managed_data_source_name or "custom-data-source",
            "schedule": "* * * * *",
            "template": {
                "spec": {
                    "source": {
                        "registry": {
                            "url": source_url or DEFAULT_FEDORA_REGISTRY_URL,
                            "pullMethod": "node",
                        }
                    },
                    "storage": {"resources": {"requests": {"storage": "10Gi"}}},
                }
            },
        },
    }


def wait_for_condition_message_value(resource, expected_message):
    def _is_expected_message_in_conditions(_expected_message):
        return any(
            [
                condition["message"] == _expected_message
                for condition in resource.instance.status.conditions
            ]
        )

    LOGGER.info(
        f"Verify {resource.name} conditions contain expected message: {expected_message}"
    )
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_5MIN,
            sleep=5,
            func=_is_expected_message_in_conditions,
            _expected_message=expected_message,
        ):
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"{resource.name} condition message does not match expected message {expected_message}, conditions: "
            f"{resource.instance.status.conditions}"
        )
        raise


def wait_for_deleted_data_import_crons(data_import_crons):
    def _get_existing_data_import_crons(_data_import_crons, _auto_boot_sources):
        return [
            data_import_cron.name
            for data_import_cron in _data_import_crons
            if data_import_cron.exists
            and re.sub(DATA_IMPORT_CRON_SUFFIX, "", data_import_cron.name)
            in _auto_boot_sources
        ]

    LOGGER.info("Wait for DataImportCrons deletion.")
    auto_boot_sources = matrix_auto_boot_sources()
    sample = None
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_2MIN,
            sleep=5,
            func=_get_existing_data_import_crons,
            _data_import_crons=data_import_crons,
            _auto_boot_sources=auto_boot_sources,
        ):
            if not sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Some DataImportCrons are not deleted: {sample}")
        raise


@contextmanager
def vm_with_data_source(
    data_source,
    namespace,
    client,
    template_labels,
    start_vm=True,
    non_existing_pvc=False,
):
    with VirtualMachineForTestsFromTemplate(
        name=f"{data_source.name}-vm",
        namespace=namespace.name,
        client=client,
        labels=template_labels,
        data_source=data_source,
        non_existing_pvc=non_existing_pvc,
    ) as vm:
        if start_vm:
            running_vm(vm=vm)
        yield vm


def template_labels(os):
    return Template.generate_template_labels(
        os=os,
        workload=Template.Workload.SERVER,
        flavor=Template.Flavor.TINY,
    )


def enable_common_boot_image_import_feature_gate_wait_for_data_import_cron(
    hco_resource, admin_client, namespace
):
    update_common_boot_image_import_feature_gate(
        hco_resource=hco_resource,
        enable_feature_gate=True,
    )
    wait_for_at_least_one_auto_update_data_import_cron(
        admin_client=admin_client, namespace=namespace
    )


def update_common_boot_image_import_feature_gate(hco_resource, enable_feature_gate):
    def _wait_for_feature_gate_update(_hco_resource, _enable_feature_gate):
        LOGGER.info(
            f"Wait for HCO {ENABLE_COMMON_BOOT_IMAGE_IMPORT_FEATURE_GATE} "
            f"feature gate to be set to {_enable_feature_gate}."
        )
        try:
            for sample in TimeoutSampler(
                wait_timeout=TIMEOUT_2MIN,
                sleep=5,
                func=lambda: _hco_resource.instance.spec.featureGates[
                    ENABLE_COMMON_BOOT_IMAGE_IMPORT_FEATURE_GATE
                ]
                == _enable_feature_gate,
            ):
                if sample:
                    return
        except TimeoutExpiredError:
            LOGGER.error(
                f"{ENABLE_COMMON_BOOT_IMAGE_IMPORT_FEATURE_GATE} was not updated to {_enable_feature_gate}"
            )
            raise

    editor = ResourceEditor(
        patches={
            hco_resource: {
                "spec": {
                    "featureGates": {
                        ENABLE_COMMON_BOOT_IMAGE_IMPORT_FEATURE_GATE: enable_feature_gate
                    }
                }
            }
        }
    )
    editor.update(backup_resources=True)
    _wait_for_feature_gate_update(
        _hco_resource=hco_resource, _enable_feature_gate=enable_feature_gate
    )


def matrix_auto_boot_sources():
    return [
        [*boot_source][0]
        for boot_source in py_config["auto_update_boot_sources_matrix"]
    ]
