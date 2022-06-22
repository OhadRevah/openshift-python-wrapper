import contextlib
import logging

from ocp_resources.job import Job
from ocp_resources.utils import TimeoutExpiredError
from pytest_testconfig import py_config


LOGGER = logging.getLogger(__name__)


@contextlib.contextmanager
def create_latency_job(latency_configmap, service_account, name=None):
    with Job(
        name=name or latency_configmap.name,
        namespace=service_account.namespace,
        service_account=service_account.name,
        restart_policy="Never",
        backoff_limit=0,
        containers=[
            {
                "name": "framework",
                "image": (
                    f"{py_config['cnv_registry_sources']['osbs']['source_map']}/"
                    "container-native-virtualization-checkup-framework"
                ),
                "imagePullPolicy": "Always",
                "env": [
                    {
                        "name": "CONFIGMAP_NAMESPACE",
                        "value": latency_configmap.namespace,
                    },
                    {"name": "CONFIGMAP_NAME", "value": latency_configmap.name},
                ],
            }
        ],
    ) as job:
        yield job


def compose_configmap_data(
    cluster_role,
    network_attachment_definition_namespace,
    network_attachment_definition_name,
):
    data_dict = {
        "spec.image": (
            f"{py_config['cnv_registry_sources']['osbs']['source_map']}"
            "/container-native-virtualization-vm-network-latency-checkup"
        ),
        "spec.timeout": "5m",
        "spec.clusterRoles": cluster_role,
        "spec.param.network_attachment_definition_namespace": network_attachment_definition_namespace,
        "spec.param.network_attachment_definition_name": network_attachment_definition_name,
    }

    return data_dict


def assert_successful_checkup(configmap, job):
    try:
        job.wait_for_condition(
            condition=job.Condition.COMPLETE, status=job.Condition.Status.TRUE
        )
        configmap_data = configmap.instance.data
        assert (
            "true" in configmap_data["status.succeeded"]
        ), f"Checkup failed. Reported reason - {configmap_data['status.failureReason']}"
    except TimeoutExpiredError:
        LOGGER.error(
            f"Couldn't run checkup. Framework job failed. status - {job.instance.status}"
        )
        raise
