import logging
from copy import deepcopy

import pytest
from ocp_resources.daemonset import DaemonSet
from ocp_resources.resource import ResourceEditor

from utilities.constants import CLUSTER_NETWORK_ADDONS_OPERATOR
from utilities.hco import wait_for_hco_conditions
from utilities.infra import get_pod_by_name_prefix


LOGGER = logging.getLogger(__name__)
NON_EXISTS_IMAGE = "non-exists-image-test-cnao-alerts"


@pytest.fixture()
def bad_cnao_deployment_linux_bridge(csv_scope_session):
    linux_bridge_image = "LINUX_BRIDGE_IMAGE"
    csv_dict = deepcopy(csv_scope_session.instance.to_dict())
    for deployment in csv_dict["spec"]["install"]["spec"]["deployments"]:
        if deployment["name"] == CLUSTER_NETWORK_ADDONS_OPERATOR:
            deployment_env = deployment["spec"]["template"]["spec"]["containers"][0][
                "env"
            ]
            for env in deployment_env:
                if env["name"] == linux_bridge_image:
                    LOGGER.info(
                        f"Replacing {linux_bridge_image} {env['value']} with {NON_EXISTS_IMAGE}"
                    )
                    env["value"] = NON_EXISTS_IMAGE

    return csv_dict


@pytest.fixture()
def bad_cnao_operator(csv_scope_session):
    operator_image = "OPERATOR_IMAGE"
    csv_dict = deepcopy(csv_scope_session.instance.to_dict())
    for deployment in csv_dict["spec"]["install"]["spec"]["deployments"]:
        if deployment["name"] == CLUSTER_NETWORK_ADDONS_OPERATOR:
            containers = deployment["spec"]["template"]["spec"]["containers"][0]
            containers["image"] = NON_EXISTS_IMAGE
            deployment_env = containers["env"]
            for env in deployment_env:
                if env["name"] == operator_image:
                    LOGGER.info(
                        f"Replacing {operator_image} {env['value']} with {NON_EXISTS_IMAGE}"
                    )
                    env["value"] = NON_EXISTS_IMAGE

    return csv_dict


@pytest.fixture()
def invalid_cnao_linux_bridge(
    admin_client, hco_namespace, csv_scope_session, bad_cnao_deployment_linux_bridge
):
    with ResourceEditor(patches={csv_scope_session: bad_cnao_deployment_linux_bridge}):
        yield


@pytest.fixture()
def invalid_cnao_operator(
    admin_client, hco_namespace, csv_scope_session, bad_cnao_operator
):
    with ResourceEditor(patches={csv_scope_session: bad_cnao_operator}):
        yield

    linux_bridge_plugin = "kube-cni-linux-bridge-plugin"
    linux_bridge_pods = get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix=linux_bridge_plugin,
        namespace=hco_namespace.name,
        get_all=True,
    )

    [pod.delete() for pod in linux_bridge_pods]
    [pod.wait_deleted() for pod in linux_bridge_pods]

    linux_bridge_plugin_ds = DaemonSet(
        name=linux_bridge_plugin, namespace=hco_namespace.name
    )
    linux_bridge_plugin_ds.wait_until_deployed()


@pytest.fixture()
def hco_ready(admin_client, hco_namespace):
    yield
    get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix=CLUSTER_NETWORK_ADDONS_OPERATOR,
        namespace=hco_namespace.name,
    ).delete(wait=True)

    wait_for_hco_conditions(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.mark.polarion("CNV-7274")
def test_cnao_not_ready(self, hco_ready, invalid_cnao_linux_bridge, prometheus):
    prometheus.alert_sampler(alert="NetworkAddonsConfigNotReady")


@pytest.mark.polarion("CNV-7275")
def test_cnao_is_down(self, hco_ready, invalid_cnao_operator, prometheus):
    prometheus.alert_sampler(alert="CnaoDown")
