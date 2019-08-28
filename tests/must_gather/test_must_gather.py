# -*- coding: utf-8 -*-

import os

import pytest
from pytest_testconfig import config as py_config
from resources.namespace import Namespace
from resources.network_addons_config import NetworkAddonsConfig
from resources.network_attachment_definition import NetworkAttachmentDefinition
from resources.node_network_state import NodeNetworkState
from resources.pod import Pod
from resources.template import Template
from resources.virtual_machine import VirtualMachine
from tests.must_gather import utils


HCO_NS = py_config["hco_namespace"]


@pytest.mark.parametrize(
    ("resource_type", "resource_path", "checks"),
    [
        pytest.param(
            NodeNetworkState,
            "cluster-scoped-resources/nmstate.io/nodenetworkstates/{name}.yaml",
            (("spec",), ("metadata", "uid"), ("metadata", "name")),
            marks=(pytest.mark.polarion("CNV-2707")),
        ),
        pytest.param(
            NetworkAddonsConfig,
            "cluster-scoped-resources/networkaddonsoperator.network"
            ".kubevirt.io/networkaddonsconfigs/{name}.yaml",
            (("spec",), ("metadata", "uid"), ("metadata", "name")),
            marks=(pytest.mark.polarion("CNV-2707")),
        ),
        pytest.param(
            NetworkAttachmentDefinition,
            "namespaces/{namespace}/k8s.cni.cncf.io/"
            "network-attachment-definitions/{name}.yaml",
            (("spec",), ("metadata", "uid"), ("metadata", "name")),
            marks=(pytest.mark.polarion("CNV-2720")),
        ),
        pytest.param(
            VirtualMachine,
            "namespaces/{namespace}/kubevirt.io/virtualmachines/{name}.yaml",
            (("spec",), ("metadata", "uid"), ("metadata", "name")),
            marks=(pytest.mark.polarion("CNV-2720")),
        ),
    ],
)
def test_resource(
    cnv_must_gather, default_client, resource_type, resource_path, checks
):
    utils.check_list_of_resources(
        default_client=default_client,
        resource_type=resource_type,
        temp_dir=cnv_must_gather,
        resource_path=resource_path,
        checks=checks,
    )


@pytest.mark.parametrize(
    "namespace", [pytest.param(HCO_NS, marks=(pytest.mark.polarion("CNV-2982")))]
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
        pytest.param(
            "kubemacpool-leader=true",
            marks=(pytest.mark.polarion("CNV-2983")),
            id="kubemacpool-mac-controller-manager_pods",
        ),
        pytest.param(
            "name=nmstate-handler",
            marks=(pytest.mark.polarion("CNV-2984")),
            id="nmstate-handler_pods",
        ),
        pytest.param(
            "name=cluster-network-addons-operator",
            marks=(pytest.mark.polarion("CNV-2985")),
            id="cluster-network-addons-operator_pods",
        ),
        pytest.param(
            "app=ovs-cni", marks=(pytest.mark.polarion("CNV-2986")), id="ovs-cni_pods"
        ),
    ],
)
def test_pods(cnv_must_gather, default_client, label_selector):
    utils.check_list_of_resources(
        default_client=default_client,
        resource_type=Pod,
        temp_dir=cnv_must_gather,
        resource_path="namespaces/{namespace}/pods/{name}/{name}.yaml",
        checks=(("metadata", "uid"), ("metadata", "name")),
        namespace=HCO_NS,
        label_selector=label_selector,
    )


@pytest.mark.polarion("CNV-2727")
def test_template_in_openshift_ns_data(cnv_must_gather, default_client):
    template_resource = list(
        Template.get(default_client, singular_name="template", namespace="openshift")
    )
    template_log = os.path.join(
        cnv_must_gather, "namespaces/openshift/templates/openshift.yaml"
    )
    with open(template_log, "r") as fd:
        data = fd.read()
    assert len(template_resource) == data.count(
        f"apiVersion: {template_resource[0].api_version}"
    )


@pytest.mark.polarion("CNV-2720")
def test_node_bridges(cnv_must_gather, node_gather_pods):
    utils.check_node_resource(
        temp_dir=cnv_must_gather,
        cmd=["ip", "-o", "link", "show", "type", "bridge"],
        node_gather_pods=node_gather_pods,
        results_file="bridge",
    )
