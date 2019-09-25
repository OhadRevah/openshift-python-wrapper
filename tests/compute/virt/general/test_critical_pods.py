"""
Check that KubeVirt infra pods are critical
"""

import json
import logging

import pytest
from pytest_testconfig import config as py_config
from resources.pod import Pod


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def virt_pods(request, default_client):
    podprefix = request.param
    pods_list = list(
        Pod.get(
            default_client,
            namespace=py_config["hco_namespace"],
            label_selector=f"kubevirt.io={podprefix}",
        )
    )
    assert pods_list, f"No pods found for {podprefix}"
    yield pods_list


@pytest.mark.parametrize(
    "virt_pods",
    [
        pytest.param("virt-api", marks=(pytest.mark.polarion("CNV-788"))),
        pytest.param("virt-controller", marks=(pytest.mark.polarion("CNV-788"))),
        pytest.param("virt-handler", marks=(pytest.mark.polarion("CNV-788"))),
    ],
    indirect=True,
)
def test_kubevirt_pods_are_critical(virt_pods):
    """
    Positive: ensure infra pods are critical
    """
    for pod in virt_pods:
        annotations = pod.instance.metadata.annotations

        LOGGER.info(f"Check {pod.name} marked as critical-pod")
        assert (
            annotations.get("scheduler.alpha.kubernetes.io/critical-pod") == ""
        ), f"Expected {pod.name} to be a critical pod"

        LOGGER.info(f"Check that {pod.name} has CriticalAddonsOnly tolerations")
        toleration_data = annotations.get("scheduler.alpha.kubernetes.io/tolerations")
        assert toleration_data, f"Expected {pod.name} to have tolerations assigned"
        assert {"key": "CriticalAddonsOnly", "operator": "Exists"} in json.loads(
            toleration_data
        ), f"Expected {pod.name} to have CriticalAddonsOnly toleration"
