"""
Check that KubeVirt infra pods are critical
"""

import logging

import pytest
from ocp_resources.pod import Pod
from pytest_testconfig import config as py_config


pytestmark = pytest.mark.post_upgrade


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def virt_pods(request, admin_client):
    podprefix = request.param
    pods_list = list(
        Pod.get(
            admin_client,
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
        LOGGER.info(f"Check {pod.name} marked as critical-pod")
        assert (
            pod.instance.metadata.annotations.get(
                "scheduler.alpha.kubernetes.io/critical-pod"
            )
            == ""
        ), f"Expected {pod.name} to be a critical pod"

        LOGGER.info(f"Check that {pod.name} has CriticalAddonsOnly tolerations")
        toleration_data = pod.instance.to_dict()["spec"].get("tolerations", [])
        assert toleration_data, f"Expected {pod.name} to have tolerations assigned"
        assert [
            entry
            for entry in toleration_data
            if entry == {"key": "CriticalAddonsOnly", "operator": "Exists"}
        ], f"Expected {pod.name} to have CriticalAddonsOnly toleration"
