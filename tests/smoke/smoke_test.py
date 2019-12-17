import logging

import pytest
from pytest_testconfig import config as py_config
from resources.deployment import Deployment
from resources.hyperconverged import HyperConverged
from resources.pod import Pod


LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def hco_operator(default_client):
    pods = list(
        Pod.get(dyn_client=default_client, namespace=py_config["hco_namespace"])
    )
    hco_operator_pod = list(filter(lambda x: "hco-operator" in x.name, pods))[0]
    return hco_operator_pod


@pytest.fixture()
def deployments(default_client):
    return Deployment.get(default_client, namespace=py_config["hco_namespace"])


@pytest.fixture()
def hyper_converged(default_client):
    return HyperConverged.get(
        dyn_client=default_client, namespace=py_config["hco_namespace"]
    )


@pytest.mark.smoke
def test_cnv_deployment(default_client, hco_operator, deployments, hyper_converged):
    LOGGER.info("Wait for HCO operator to be ready")
    hco_operator.wait_for_condition(condition="Ready", status="True")

    LOGGER.info("Wait for number of replicas = number of updated replicas")
    for deploy in deployments:
        deploy.wait_until_avail_replicas(timeout=10)

    LOGGER.info("Wait for HCO to be available.")
    for hco in hyper_converged:
        hco.wait_for_condition(condition="Available", status="True")
