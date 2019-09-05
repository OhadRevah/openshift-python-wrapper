# -*- coding: utf-8 -*-

from tests.must_gather import utils
from resources.network_addons_config import NetworkAddonsConfig
from resources.namespace import Namespace
from resources.pod import Pod
import pytest


LINUX_BRIDGE_NS = "linux-bridge"


@pytest.mark.polarion("CNV-2707")
def test_networkaddonsconfig(cnv_must_gather, default_client):
    utils.check_list_of_resources(
        default_client=default_client,
        resource_type=NetworkAddonsConfig,
        temp_dir=cnv_must_gather,
        resource_path="cluster-scoped-resources/networkaddonsoperator.network"
        ".kubevirt.io/networkaddonsconfigs/{name}.yaml",
        checks=(("spec",), ("metadata", "uid"), ("metadata", "name")),
    )


@pytest.mark.parametrize(
    "namespace",
    [pytest.param("linux-bridge", marks=(pytest.mark.polarion("CNV-2982")))],
)
def test_namespace(cnv_must_gather, namespace):
    utils.check_resource(
        resource=Namespace,
        resource_name=namespace,
        temp_dir=cnv_must_gather,
        resource_path="namespaces/{name}/{name}.yaml",
        checks=(("spec",), ("metadata", "name"), ("metadata", "uid")),
    )


@pytest.mark.parametrize(
    "label_selector",
    [
        pytest.param(
            "app=bridge-marker",
            marks=(pytest.mark.polarion("CNV-2721")),
            id="test_bridge_marker_pods",
        ),
        pytest.param(
            "name=kube-cni-linux-bridge-plugin",
            marks=(pytest.mark.polarion("CNV-2705")),
            id="test_kube_cni_pods",
        ),
    ],
)
def test_linux_bridge_pods_data(cnv_must_gather, default_client, label_selector):
    utils.check_list_of_resources(
        default_client=default_client,
        resource_type=Pod,
        temp_dir=cnv_must_gather,
        resource_path="namespaces/linux-bridge/pods/{name}/{name}.yaml",
        checks=(("metadata", "uid"), ("metadata", "name")),
        namespace=LINUX_BRIDGE_NS,
        label_selector=label_selector,
    )
