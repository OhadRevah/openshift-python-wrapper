import logging
from contextlib import contextmanager

from ocp_resources.template import Template
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler

from tests.compute.ssp.supported_os.common_templates.golden_images.update_boot_source.constants import (
    DEFAULT_FEDORA_REGISTRY_URL,
)
from utilities.constants import TIMEOUT_5MIN
from utilities.virt import VirtualMachineForTestsFromTemplate, running_vm


LOGGER = logging.getLogger(__name__)


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
