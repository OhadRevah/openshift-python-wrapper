from copy import deepcopy

import pytest
from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.resource import ResourceEditor
from ocp_resources.utils import TimeoutSampler

from utilities.constants import TIMEOUT_10MIN, TIMEOUT_20MIN
from utilities.infra import get_pod_by_name_prefix


NON_EXISTS_IMAGE = "non-exists-image-test-cnao-alerts"


def sampler_alert(prometheus, query):
    alert_prefix = "ALERTS{alertname="
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=1,
        func=prometheus.query,
        query=f"{alert_prefix}{query}",
    )
    for sample in sampler:
        result = sample["data"]["result"]
        if result and result[0]["value"][-1] == "1":
            return


@pytest.fixture(scope="class")
def csv_scope_class(admin_client, hco_namespace):
    for csv in ClusterServiceVersion.get(
        dyn_client=admin_client, namespace=hco_namespace.name
    ):
        return csv


@pytest.fixture(scope="class")
def bad_cnao_deployment_linux_bridge(csv_scope_class):
    name = "cluster-network-addons-operator"
    csv_dict = deepcopy(csv_scope_class.instance.to_dict())
    for deployment in csv_dict["spec"]["install"]["spec"]["deployments"]:
        if deployment["name"] == name:
            deployment_env = deployment["spec"]["template"]["spec"]["containers"][0][
                "env"
            ]
            for env in deployment_env:
                if env["name"] == "LINUX_BRIDGE_IMAGE":
                    env["value"] = NON_EXISTS_IMAGE

    return csv_dict


@pytest.fixture(scope="class")
def bad_cnao_operator(csv_scope_class):
    name = "cluster-network-addons-operator"
    csv_dict = deepcopy(csv_scope_class.instance.to_dict())
    for deployment in csv_dict["spec"]["install"]["spec"]["deployments"]:
        if deployment["name"] == name:
            containers = deployment["spec"]["template"]["spec"]["containers"][0]
            containers["image"] = NON_EXISTS_IMAGE
            deployment_env = containers["env"]
            for env in deployment_env:
                if env["name"] == "OPERATOR_IMAGE":
                    env["value"] = NON_EXISTS_IMAGE

    return csv_dict


@pytest.fixture(scope="class")
def invalid_cnao_linux_bridge(
    admin_client, hco_namespace, csv_scope_class, bad_cnao_deployment_linux_bridge
):
    with ResourceEditor(patches={csv_scope_class: bad_cnao_deployment_linux_bridge}):
        yield


@pytest.fixture(scope="class")
def invalid_cnao_operator(
    admin_client, hco_namespace, csv_scope_class, bad_cnao_operator
):
    with ResourceEditor(patches={csv_scope_class: bad_cnao_operator}):
        yield


@pytest.fixture(scope="class")
def hco_ready(admin_client, hco_namespace):
    yield
    pods_to_delete = get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix="kube-cni-linux-bridge-plugin",
        namespace=hco_namespace.name,
        get_all=True,
    )

    pods_to_delete.append(
        get_pod_by_name_prefix(
            dyn_client=admin_client,
            pod_prefix="cluster-network-addons-operator",
            namespace=hco_namespace.name,
        )
    )
    [pod.delete() for pod in pods_to_delete]

    hco_operator_pod = get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix="hco-operator",
        namespace=hco_namespace.name,
    )

    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_20MIN,
        sleep=1,
        func=lambda: hco_operator_pod.instance.status.containerStatuses[0].ready,
    )
    for sample in sampler:
        if sample:
            return


class TestInvalidCNAO:
    @pytest.mark.polarion("CNV-7274")
    def test_cnao_not_ready(self, hco_ready, invalid_cnao_linux_bridge, prometheus):
        sampler_alert(prometheus=prometheus, query="'NetworkAddonsConfigNotReady'}")

    @pytest.mark.polarion("CNV-7275")
    def test_cnao_is_down(self, hco_ready, invalid_cnao_operator, prometheus):
        sampler_alert(prometheus=prometheus, query="'CnaoDown'}")
