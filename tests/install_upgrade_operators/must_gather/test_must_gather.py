# -*- coding: utf-8 -*-

import os
import re

import pytest
import yaml
from ocp_resources.api_service import APIService
from ocp_resources.cdi_config import CDIConfig
from ocp_resources.imagestreamtag import ImageStreamTag
from ocp_resources.mutating_webhook_config import MutatingWebhookConfiguration
from ocp_resources.namespace import Namespace
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.network_attachment_definition import NetworkAttachmentDefinition
from ocp_resources.node_network_state import NodeNetworkState
from ocp_resources.pod import Pod
from ocp_resources.template import Template
from ocp_resources.validating_webhook_config import ValidatingWebhookConfiguration
from ocp_resources.virtual_machine import VirtualMachine
from pytest_testconfig import config as py_config

from tests.install_upgrade_operators.must_gather import utils
from utilities.constants import (
    BRIDGE_MARKER,
    KUBE_CNI_LINUX_BRIDGE_PLUGIN,
    KUBEMACPOOL_MAC_RANGE_CONFIG,
    NMSTATE_HANDLER,
)
from utilities.infra import BUG_STATUS_CLOSED


pytestmark = pytest.mark.sno


@pytest.mark.parametrize(
    ("resource_type", "resource_path", "checks"),
    [
        pytest.param(
            NodeNetworkState,
            "cluster-scoped-resources/nmstate.io/nodenetworkstates/{name}.yaml",
            (("metadata", "uid"), ("metadata", "name")),
            marks=(pytest.mark.polarion("CNV-2707")),
            id="test_nodenetworkstate_resources",
        ),
        pytest.param(
            NetworkAddonsConfig,
            "cluster-scoped-resources/networkaddonsoperator.network"
            ".kubevirt.io/networkaddonsconfigs/{name}.yaml",
            (("spec",), ("metadata", "uid"), ("metadata", "name")),
            marks=(pytest.mark.polarion("CNV-3042")),
            id="test_networkaddonsoperator_resources",
        ),
        pytest.param(
            NetworkAttachmentDefinition,
            "namespaces/{namespace}/k8s.cni.cncf.io/"
            "network-attachment-definitions/{name}.yaml",
            (("spec",), ("metadata", "uid"), ("metadata", "name")),
            marks=(pytest.mark.polarion("CNV-2720")),
            id="test_network_attachment_definitions_resources",
        ),
        pytest.param(
            VirtualMachine,
            "namespaces/{namespace}/kubevirt.io/virtualmachines/custom/{name}.yaml",
            (("spec",), ("metadata", "uid"), ("metadata", "name")),
            marks=(pytest.mark.polarion("CNV-3043")),
            id="test_virtualmachine_resources",
        ),
        pytest.param(
            CDIConfig,
            "cluster-scoped-resources/cdiconfigs.cdi.kubevirt.io/{name}.yaml",
            (
                ("spec",),
                ("metadata", "uid"),
                ("metadata", "name"),
            ),
            marks=(pytest.mark.polarion("CNV-3373")),
            id="test_cdi_config_resources",
        ),
    ],
    indirect=["resource_type"],
)
def test_resource_type(
    cnv_must_gather, admin_client, resource_type, resource_path, checks
):
    utils.check_list_of_resources(
        dyn_client=admin_client,
        resource_type=resource_type,
        temp_dir=cnv_must_gather,
        resource_path=resource_path,
        checks=checks,
    )


@pytest.mark.parametrize(
    "namespace",
    [
        pytest.param(
            py_config["hco_namespace"],
            marks=(pytest.mark.polarion("CNV-2982")),
            id="test_hco_namespace",
        )
    ],
)
def test_namespace(cnv_must_gather, namespace):
    utils.check_resource(
        resource=Namespace,
        resource_name=namespace,
        temp_dir=cnv_must_gather,
        resource_path="namespaces/{name}/{name}.yaml",
        checks=(("spec",), ("metadata", "name"), ("metadata", "uid")),
    )


@pytest.mark.polarion("CNV-5885")
def test_no_upstream_only_namespaces(cnv_must_gather):
    """
    After running must-gather command on the cluster, there are some upstream-only namespaces
    present. We counter "POD Error from server (NotFound)" in the logs as there no upstream-only
    namespaces present. This test case will ensure that there is no logs showing "POD Error from
    server (NotFound)" in the must-gather command execution.
    """
    upstream_namespaces = [
        "kubevirt-hyperconverged",
        "cluster-network-addons",
        "sriov-network-operator",
        "kubevirt-web-ui",
        "cdi",
    ]
    ns_errors = {"upstream": [], "unexpected": []}
    with open(utils.get_must_gather_output_file(cnv_must_gather)) as cmd_output:
        for line in cmd_output.readlines():
            match_output = re.search(
                r"POD Error from server \(NotFound\): namespaces \"(\S+)\" not found",
                line,
            )
            if match_output:
                found_ns = match_output.group(1)
                if found_ns in upstream_namespaces:
                    ns_errors["upstream"].append(found_ns)
                else:
                    ns_errors["unexpected"].append(found_ns)
    assert not any(
        ns_errors.values()
    ), f"Found namespace errors in must-gather. {ns_errors}"


@pytest.mark.parametrize(
    "label_selector, resource_namespace",
    [
        pytest.param(
            f"app={BRIDGE_MARKER}",
            py_config["hco_namespace"],
            marks=(pytest.mark.polarion("CNV-2721")),
            id="test_bridge_marker_pods",
        ),
        pytest.param(
            f"name={KUBE_CNI_LINUX_BRIDGE_PLUGIN}",
            py_config["hco_namespace"],
            marks=(pytest.mark.polarion("CNV-2705")),
            id="test_kube_cni_pods",
        ),
        pytest.param(
            "kubemacpool-leader=true",
            py_config["hco_namespace"],
            marks=(pytest.mark.polarion("CNV-2983")),
            id="kubemacpool-mac-controller-manager_pods",
        ),
        pytest.param(
            f"name={NMSTATE_HANDLER}",
            py_config["hco_namespace"],
            marks=(pytest.mark.polarion("CNV-2984")),
            id=f"{NMSTATE_HANDLER}_pods",
        ),
        pytest.param(
            "name=cluster-network-addons-operator",
            py_config["hco_namespace"],
            marks=(pytest.mark.polarion("CNV-2985")),
            id="cluster-network-addons-operator_pods",
        ),
        pytest.param(
            "app=ovs-cni",
            py_config["hco_namespace"],
            marks=(pytest.mark.polarion("CNV-2986")),
            id="ovs-cni_pods",
        ),
        pytest.param(
            "app=kubemacpool",
            py_config["hco_namespace"],
            marks=(pytest.mark.polarion("CNV-2718")),
            id="kubemacpool_pods",
        ),
        pytest.param(
            "app=sriov-device-plugin",
            "sriov-network-operator",
            marks=(pytest.mark.polarion("CNV-2710")),
            id="test_sriov_device_plugin_pods",
        ),
        pytest.param(
            "app=sriov-cni",
            "sriov-network-operator",
            marks=(pytest.mark.polarion("CNV-2709")),
            id="test_sriov_cni_pods",
        ),
        pytest.param(
            "app=containerized-data-importer",
            py_config["hco_namespace"],
            marks=(pytest.mark.polarion("CNV-3369")),
            id="test_cdi_deployment_pods",
        ),
    ],
)
def test_pods(cnv_must_gather, admin_client, label_selector, resource_namespace):
    utils.check_list_of_resources(
        dyn_client=admin_client,
        resource_type=Pod,
        temp_dir=cnv_must_gather,
        resource_path="namespaces/{namespace}/pods/{name}/{name}.yaml",
        checks=(("metadata", "uid"), ("metadata", "name")),
        namespace=resource_namespace,
        label_selector=label_selector,
    )


@pytest.mark.polarion("CNV-2727")
def test_template_in_openshift_ns_data(cnv_must_gather, admin_client):
    template_resource = list(
        Template.get(admin_client, singular_name="template", namespace="openshift")
    )
    template_log = os.path.join(
        cnv_must_gather, "namespaces/openshift/templates/openshift.yaml"
    )
    with open(template_log, "r") as fd:
        data = fd.read()
    assert len(template_resource) == data.count(f"kind: {template_resource[0].kind}")


@pytest.mark.polarion("CNV-2809")
def test_node_nftables(skip_no_rhcos, cnv_must_gather, utility_pods):
    for pod in utility_pods:
        node_name = pod.node.name
        nft_files = [
            file
            for file in os.listdir(f"{cnv_must_gather}/nodes/{node_name}")
            if file.startswith("nft")
        ]
        nftables = pod.execute(
            command=["bash", "-c", "nft list tables 2>/dev/null"]
        ).splitlines()
        utils.assert_nft_collection(
            nft_files=nft_files, nftables=nftables, node_name=node_name
        )
        for table in nftables:
            # table is a string of the form: "table {family} {name}"
            family, name = table.split()[1:3]
            utils.check_node_resource(
                temp_dir=cnv_must_gather,
                cmd=["bash", "-c", f"nft list {table} 2>/dev/null"],
                utility_pod=pod,
                results_file=f"nft-{family}-{name}",
                compare_method="nft_compare",
            )


@pytest.mark.parametrize(
    "cmd, results_file, compare_method",
    [
        pytest.param(
            ["ip", "-o", "link", "show", "type", "bridge"],
            "bridge",
            "simple_compare",
            marks=(
                pytest.mark.polarion("CNV-2730"),
                pytest.mark.bugzilla(
                    1952036, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
            ),
            id="test_nodes_bridge_data",
        ),
        pytest.param(
            ["/bin/bash", "-c", "ls -l /host/var/lib/cni/bin"],
            "var-lib-cni-bin",
            "simple_compare",
            marks=(
                pytest.mark.polarion("CNV-2810"),
                pytest.mark.bugzilla(
                    1952041, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
            ),
            id="test_nodes_cni_bin_data",
        ),
        pytest.param(
            ["ip", "a"],
            "ip.txt",
            "ip_compare",
            marks=(
                pytest.mark.polarion("CNV-2732"),
                pytest.mark.bugzilla(
                    1952052, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
            ),
            id="test_nodes_ip_data",
        ),
    ],
)
def test_node_resource(
    cnv_must_gather, utility_pods, cmd, results_file, compare_method
):
    for pod in utility_pods:
        utils.check_node_resource(
            temp_dir=cnv_must_gather,
            cmd=cmd,
            utility_pod=pod,
            results_file=results_file,
            compare_method=compare_method,
        )


@pytest.mark.parametrize(
    "command, results_file, compare_method",
    [
        pytest.param(
            ["ls", "-al", "/host/dev/vfio"],
            "dev_vfio",
            "simple_compare",
            marks=(pytest.mark.polarion("CNV-3045")),
            id="test_dev_vfio_on_node",
        ),
    ],
)
def test_node_sriov_resource(
    skip_when_no_sriov,
    cnv_must_gather,
    utility_pods,
    command,
    results_file,
    compare_method,
):
    for pod in utility_pods:
        utils.check_node_resource(
            temp_dir=cnv_must_gather,
            cmd=command,
            utility_pod=pod,
            results_file=results_file,
            compare_method=compare_method,
        )


@pytest.mark.polarion("CNV-2801")
def test_nmstate_config_data(cnv_must_gather, admin_client):
    utils.check_list_of_resources(
        dyn_client=admin_client,
        resource_type=NodeNetworkState,
        temp_dir=cnv_must_gather,
        resource_path="cluster-scoped-resources/nmstate.io/nodenetworkstates/{name}.yaml",
        checks=(("metadata", "name"), ("metadata", "uid")),
    )


@pytest.mark.parametrize(
    "label_selector",
    [pytest.param({"app": "cni-plugins"}, marks=(pytest.mark.polarion("CNV-2715")))],
)
def test_logs_gathering(cnv_must_gather, running_hco_containers, label_selector):
    utils.check_logs(
        cnv_must_gather=cnv_must_gather,
        running_hco_containers=running_hco_containers,
        label_selector=label_selector,
        namespace=py_config["hco_namespace"],
    )


@pytest.mark.parametrize(
    "label_selector",
    [
        pytest.param(
            {"app": "sriov-device-plugin"},
            marks=(pytest.mark.polarion("CNV-5355")),
            id="test_sriov_device_plugin_logs",
        ),
        pytest.param(
            {"app": "sriov-cni"},
            marks=(pytest.mark.polarion("CNV-5354")),
            id="test_sriov_cni_logs",
        ),
    ],
)
def test_sriov_logs_gathering(
    skip_when_no_sriov,
    sriov_namespace,
    cnv_must_gather,
    running_sriov_network_operator_containers,
    label_selector,
):
    utils.check_logs(
        cnv_must_gather=cnv_must_gather,
        running_hco_containers=running_sriov_network_operator_containers,
        label_selector=label_selector,
        namespace=sriov_namespace.name,
    )


@pytest.mark.parametrize(
    ("file_suffix", "section_title", "format_regex"),
    [
        pytest.param(
            "ip.txt", None, "\\A1: lo: .*", marks=(pytest.mark.polarion("CNV-2734"))
        ),
        pytest.param(
            "bridge.txt",
            "bridge fdb show:",
            "^(?:[0-9a-fA-F]:?){12} dev .*$",
            marks=(pytest.mark.polarion("CNV-2735")),
        ),
        pytest.param(
            "bridge.txt",
            "bridge vlan show:",
            ".*1 PVID .*untagged$",
            marks=(pytest.mark.polarion("CNV-2736")),
        ),
        pytest.param(
            "iptables.txt",
            "Filter table:",
            "^Chain INPUT \\(policy ACCEPT\\)$",
            marks=(
                pytest.mark.polarion("CNV-2737"),
                pytest.mark.bugzilla(
                    1959039, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
            ),
        ),
        pytest.param(
            "iptables.txt",
            "NAT table:",
            "^Chain PREROUTING \\(policy ACCEPT\\)$",
            marks=(
                pytest.mark.polarion("CNV-2741"),
                pytest.mark.bugzilla(
                    1959039, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
                ),
            ),
        ),
        pytest.param(
            "qemu.log",
            None,
            "-name guest={namespace}_{name},debug-threads=on \\\\$",
            marks=(pytest.mark.polarion("CNV-2725")),
        ),
        pytest.param(
            "dumpxml.xml",
            None,
            "^ +<name>{namespace}_{name}</name>$",
            marks=(pytest.mark.polarion("CNV-3477")),
        ),
    ],
)
def test_data_collected_from_virt_launcher(
    cnv_must_gather, running_vm, file_suffix, section_title, format_regex
):
    virt_launcher = running_vm.vmi.virt_launcher_pod

    gathered_data_path = (
        f"{cnv_must_gather}/namespaces/{virt_launcher.namespace}/vms/"
        f"{virt_launcher.name}.{file_suffix}"
    )

    assert os.path.exists(
        gathered_data_path
    ), "Have not found gathered data file on given path"

    with open(gathered_data_path) as f:
        gathered_data = f.read()

    # If the gathered data file consists of multiple sections, extract the one
    # we are interested in.
    if section_title:
        matches = re.findall(
            f"^{section_title}\n"  # title
            "^#+\n"  # title separator
            "(.*?)"  # capture section body
            "(?:^#+\n|\\Z)",  # next title separator or end of data
            gathered_data,
            re.MULTILINE | re.DOTALL,
        )
        assert matches, (
            "Section has not been found in gathered data.\n"
            f"Section title: {section_title}\n"
            f"Gathered data: {gathered_data}"
        )
        gathered_data = matches[0]

    if "name" in format_regex and "namespace" in format_regex:
        format_regex = format_regex.format(
            namespace=running_vm.namespace, name=running_vm.name
        )

    # Make sure that gathered data roughly matches expected format.
    assert re.search(format_regex, gathered_data, re.MULTILINE | re.IGNORECASE), (
        "Gathered data are not matching expected format.\n"
        f"Expected format:\n{format_regex}\n "
        f"Gathered data:\n{gathered_data}"
    )


@pytest.mark.parametrize(
    "config_map_by_name, has_owner",
    [
        pytest.param(
            [KUBEMACPOOL_MAC_RANGE_CONFIG, py_config["hco_namespace"]],
            True,
            marks=(pytest.mark.polarion("CNV-2718")),
            id="test_config_map_kubemacpool-mac-range-config",
        ),
    ],
    indirect=["config_map_by_name"],
)
def test_gathered_config_maps(
    cnv_must_gather, config_maps_file, config_map_by_name, has_owner
):
    checks = [("metadata", "name"), ("metadata", "uid")]
    if has_owner:
        checks.append(("metadata", "ownerReferences"))
    utils.compare_resource_contents(
        resource=config_map_by_name,
        file_content=next(
            filter(
                lambda resource: resource["metadata"]["name"]
                == config_map_by_name.name,
                config_maps_file["items"],
            )
        ),
        checks=checks,
    )


@pytest.mark.polarion("CNV-2723")
def test_apiservice_resources(cnv_must_gather, admin_client):
    utils.check_list_of_resources(
        dyn_client=admin_client,
        resource_type=APIService,
        temp_dir=cnv_must_gather,
        resource_path="apiservices/{name}.yaml",
        checks=(("spec",), ("metadata", "name"), ("metadata", "uid")),
        filter_resource="kubevirt",
    )


@pytest.mark.polarion("CNV-2726")
def test_webhookconfig_resources(cnv_must_gather, admin_client):
    checks = (("metadata", "name"), ("metadata", "uid"))
    utils.check_list_of_resources(
        dyn_client=admin_client,
        resource_type=ValidatingWebhookConfiguration,
        temp_dir=cnv_must_gather,
        resource_path="webhooks/validating/{name}/validatingwebhookconfiguration.yaml",
        checks=checks,
    )
    utils.check_list_of_resources(
        dyn_client=admin_client,
        resource_type=MutatingWebhookConfiguration,
        temp_dir=cnv_must_gather,
        resource_path="webhooks/mutating/{name}/mutatingwebhookconfiguration.yaml",
        checks=checks,
    )

    for webhook_resources in [
        list(ValidatingWebhookConfiguration.get(admin_client)),
        list(MutatingWebhookConfiguration.get(admin_client)),
    ]:
        utils.compare_webhook_svc_contents(
            webhook_resources=webhook_resources,
            cnv_must_gather=cnv_must_gather,
            dyn_client=admin_client,
            checks=checks,
        )


@pytest.mark.polarion("CNV-2724")
def test_crd_resources(admin_client, cnv_must_gather, kubevirt_crd_resources):
    for kubevirt_crd_resource in kubevirt_crd_resources:
        crd_name = kubevirt_crd_resource.name
        for version in kubevirt_crd_resource.instance.spec.versions:
            resource_objs = admin_client.resources.get(
                api_version=version.name,
                kind=kubevirt_crd_resource.instance.spec.names.kind,
            )

            for resource_item in resource_objs.get().to_dict()["items"]:
                metadata = resource_item["metadata"]
                name = metadata["name"]
                if "namespace" in metadata:
                    resource_file = os.path.join(
                        cnv_must_gather,
                        f"namespaces/{metadata['namespace']}/crs/{crd_name}/{name}.yaml",
                    )
                else:
                    resource_file = os.path.join(
                        cnv_must_gather,
                        f"cluster-scoped-resources/{crd_name}/{name}.yaml",
                    )

                with open(resource_file) as resource_file:
                    file_content = yaml.safe_load(
                        resource_file.read(),
                    )
                assert name == file_content["metadata"]["name"]
                assert (
                    resource_item["metadata"]["uid"] == file_content["metadata"]["uid"]
                )


@pytest.mark.polarion("CNV-2939")
def test_imagestreamtag_resources(admin_client, cnv_must_gather):
    namespace = "openshift"
    istag_dir = os.path.join(
        cnv_must_gather,
        f"namespaces/{namespace}/image.openshift.io/imagestreamtags/",
    )

    assert len(os.listdir(istag_dir)) == len(
        list(ImageStreamTag.get(admin_client, namespace=namespace))
    )
    checks = (("metadata", "name"), ("metadata", "uid"))

    utils.check_list_of_resources(
        dyn_client=admin_client,
        resource_type=ImageStreamTag,
        temp_dir=cnv_must_gather,
        resource_path="namespaces/{namespace}/image.openshift.io/imagestreamtags/{name}.yaml",
        checks=checks,
        namespace=namespace,
        filter_resource="redhat",
    )