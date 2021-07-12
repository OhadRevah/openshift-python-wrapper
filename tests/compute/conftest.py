from contextlib import contextmanager

import pytest

from tests.compute.utils import update_hco_config, wait_for_updated_kv_value


@contextmanager
def update_cluster_cpu_model(admin_client, hco_namespace, hco_resource, cpu_model):
    with update_hco_config(
        resource=hco_resource,
        path="cpuModel",
        value=cpu_model,
    ):
        wait_for_updated_kv_value(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            path=["cpuModel"],
            value=cpu_model,
            timeout=30,
        )
        yield


@pytest.fixture(scope="module")
def cluster_cpu_model_scope_module(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_module,
    nodes_common_cpu_model,
):
    with update_cluster_cpu_model(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        hco_resource=hyperconverged_resource_scope_module,
        cpu_model=nodes_common_cpu_model,
    ):
        yield


@pytest.fixture(scope="class")
def cluster_cpu_model_scope_class(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_class,
    nodes_common_cpu_model,
):
    with update_cluster_cpu_model(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        hco_resource=hyperconverged_resource_scope_class,
        cpu_model=nodes_common_cpu_model,
    ):
        yield


@pytest.fixture()
def cluster_cpu_model_scope_function(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_function,
    nodes_common_cpu_model,
):
    with update_cluster_cpu_model(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        hco_resource=hyperconverged_resource_scope_function,
        cpu_model=nodes_common_cpu_model,
    ):
        yield
