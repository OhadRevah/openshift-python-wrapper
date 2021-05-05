import logging

import pytest
from ocp_resources.resource import ResourceEditor

from tests.metrics.utils import get_mutation_component_value_from_prometheus
from utilities.virt import Prometheus


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def prometheus():
    return Prometheus()


@pytest.fixture()
def updated_resource_with_invalid_label(request, admin_client, hco_namespace):
    res = request.param["resource"]
    resource = list(
        res.get(
            dyn_client=admin_client,
            name=request.param.get("name"),
            namespace=hco_namespace.name,
        )
    )[0]

    with ResourceEditor(
        patches={
            resource: {
                "metadata": {
                    "labels": {"test_label": "testing_invalid_label"},
                },
                "namespace": hco_namespace.name,
            }
        }
    ):
        yield


@pytest.fixture()
def mutation_count_before_change(request, prometheus):
    component_name = request.param
    LOGGER.info(f"Getting component '{component_name}' mutation count before change.")
    return get_mutation_component_value_from_prometheus(
        prometheus=prometheus,
        component_name=component_name,
    )
