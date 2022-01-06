import pytest
from ocp_resources.pod import Pod

from tests.install_upgrade_operators.hco_enablement_golden_image_updates.constants import (
    SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME,
)
from tests.install_upgrade_operators.hco_enablement_golden_image_updates.utils import (
    FG_ENABLE_COMMON_BOOT_IMAGE_IMPORT_KEY_NAME,
    HCO_CR_DATA_IMPORT_SCHEDULE_KEY,
    delete_hco_operator_pod,
    get_random_minutes_hours_fields_from_data_import_schedule,
)
from tests.install_upgrade_operators.product_upgrade.utils import get_operator_by_name
from tests.install_upgrade_operators.utils import wait_for_stabilize
from utilities.constants import HCO_OPERATOR
from utilities.infra import update_custom_resource


@pytest.fixture()
def data_import_schedule(hyperconverged_resource_scope_function):
    return hyperconverged_resource_scope_function.instance.status.get(
        HCO_CR_DATA_IMPORT_SCHEDULE_KEY
    )


@pytest.fixture()
def data_import_schedule_minute_and_hour_values(data_import_schedule):
    return get_random_minutes_hours_fields_from_data_import_schedule(
        target_string=data_import_schedule
    )


@pytest.fixture(scope="class")
def enabled_hco_featuregate_enable_common_boot_image_import(
    admin_client, hco_namespace, hyperconverged_resource_scope_class
):
    with update_custom_resource(
        patch={
            hyperconverged_resource_scope_class: {
                "spec": {
                    "featureGates": {FG_ENABLE_COMMON_BOOT_IMAGE_IMPORT_KEY_NAME: True}
                }
            }
        }
    ):
        wait_for_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)
        yield
    wait_for_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture()
def expected_ssp_cr_common_templates_with_schedule(data_import_schedule):
    return {
        SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME: [
            {
                "metadata": {
                    "annotations": {
                        "cdi.kubevirt.io/storage.bind.immediate.requested": "true",
                    },
                    "name": "rhel8-image-cron",
                },
                "spec": {
                    "garbageCollect": "Outdated",
                    "managedDataSource": "rhel8",
                    "schedule": data_import_schedule,
                    "template": {
                        "metadata": {},
                        "spec": {
                            "source": {
                                "registry": {
                                    "imageStream": "rhel8-guest",
                                    "pullMethod": "node",
                                },
                            },
                            "storage": {
                                "resources": {
                                    "requests": {
                                        "storage": "10Gi",
                                    }
                                }
                            },
                        },
                        "status": {},
                    },
                },
            },
            {
                "metadata": {
                    "annotations": {
                        "cdi.kubevirt.io/storage.bind.immediate.requested": "true",
                    },
                    "name": "rhel9-image-cron",
                },
                "spec": {
                    "garbageCollect": "Outdated",
                    "managedDataSource": "rhel9",
                    "schedule": data_import_schedule,
                    "template": {
                        "metadata": {},
                        "spec": {
                            "source": {
                                "registry": {
                                    "imageStream": "rhel9-guest",
                                    "pullMethod": "node",
                                },
                            },
                            "storage": {
                                "resources": {
                                    "requests": {
                                        "storage": "10Gi",
                                    }
                                }
                            },
                        },
                        "status": {},
                    },
                },
            },
            {
                "metadata": {
                    "annotations": {
                        "cdi.kubevirt.io/storage.bind.immediate.requested": "true",
                    },
                    "name": "centos8-image-cron",
                },
                "spec": {
                    "garbageCollect": "Outdated",
                    "managedDataSource": "centos8",
                    "schedule": data_import_schedule,
                    "template": {
                        "metadata": {},
                        "spec": {
                            "source": {
                                "registry": {
                                    "url": "docker://quay.io/kubevirt/centos8-container-disk-images",
                                },
                            },
                            "storage": {
                                "resources": {
                                    "requests": {
                                        "storage": "10Gi",
                                    }
                                }
                            },
                        },
                        "status": {},
                    },
                },
            },
            {
                "metadata": {
                    "annotations": {
                        "cdi.kubevirt.io/storage.bind.immediate.requested": "true",
                    },
                    "name": "fedora-image-cron",
                },
                "spec": {
                    "garbageCollect": "Outdated",
                    "managedDataSource": "fedora",
                    "schedule": data_import_schedule,
                    "template": {
                        "metadata": {},
                        "spec": {
                            "source": {
                                "registry": {
                                    "url": "docker://quay.io/kubevirt/fedora-container-disk-images",
                                },
                            },
                            "storage": {
                                "resources": {
                                    "requests": {
                                        "storage": "5Gi",
                                    }
                                }
                            },
                        },
                        "status": {},
                    },
                },
            },
        ]
    }


@pytest.fixture()
def deleted_hco_operator_pod(
    admin_client, hco_namespace, hyperconverged_resource_scope_function
):
    delete_hco_operator_pod(admin_client=admin_client, hco_namespace=hco_namespace)
    get_operator_by_name(
        dyn_client=admin_client,
        hco_namespace=hco_namespace.name,
        operator_name=HCO_OPERATOR,
    ).wait_for_status(status=Pod.Status.RUNNING)
    return get_random_minutes_hours_fields_from_data_import_schedule(
        target_string=hyperconverged_resource_scope_function.instance.status.get(
            HCO_CR_DATA_IMPORT_SCHEDULE_KEY
        )
    )
