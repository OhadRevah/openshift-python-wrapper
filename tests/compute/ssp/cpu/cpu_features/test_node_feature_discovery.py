"""
Test node feature discovery.
"""
from xml.etree import ElementTree

import pytest
import yaml
from pytest_testconfig import config as py_config
from resources.configmap import ConfigMap
from resources.pod import Pod
from utilities.virt import VirtualMachineForTests, fedora_vm_body


@pytest.fixture(scope="module")
def nodes_labels_dict(nodes):
    """
    Collects all labels from nodes and creates dict of cpu-models/features/kvm-info per node.
    Return dict:
    {'<node_name>': {'cpu_models': [<cpu_models>], 'cpu_features': [<cpu_features>], 'kvm-info': [<kvm-info>]}}
    """
    node_labels_dict = {}

    for node in nodes:
        node_labels_dict[node.name] = {}
        labels_dict = dict(node.instance.metadata.labels)
        node_labels_dict[node.name]["cpu_models"] = [
            label.split("cpu-model-")[1]
            for label in labels_dict
            if "feature.node.kubernetes.io/cpu-model-" in label
        ]
        node_labels_dict[node.name]["cpu_features"] = [
            label.split("cpu-feature-")[1]
            for label in labels_dict
            if "feature.node.kubernetes.io/cpu-feature-" in label
        ]
        node_labels_dict[node.name]["kvm-info"] = [
            label.split("kvm-info-cap-hyperv-")[1]
            for label in labels_dict
            if "feature.node.kubernetes.io/kvm-info-cap-hyperv-" in label
        ]

    return node_labels_dict


@pytest.fixture(scope="module")
def config_map_cpu_model_dict():
    """
    Extract CPU obsolete models and minimal CPU model from config map.
    Return dict:
    {'obsoleteCPUs': [<cpu_models>], 'minCPU': '<cpu_model>'}
    """
    cpu_plugin_map = ConfigMap(
        name="kubevirt-cpu-plugin-configmap", namespace=py_config["hco_namespace"]
    )

    return yaml.load(
        cpu_plugin_map.instance.data["cpu-plugin-configmap.yaml"], Loader=yaml.Loader,
    )


@pytest.fixture(scope="module")
def obsolete_cpus_list(config_map_cpu_model_dict):
    return config_map_cpu_model_dict["obsoleteCPUs"]


@pytest.fixture()
def libvirt_min_cpu_features_list(
    config_map_cpu_model_dict, cpu_test_vm, default_client
):
    """
    Extract minimal CPU model features from libvirt/cpu_map xml.
    """
    exec_pod = list(
        Pod.get(dyn_client=default_client, namespace=cpu_test_vm.namespace)
    )[0]
    stdout = exec_pod.execute(
        command=[
            "cat",
            f"/usr/share/libvirt/cpu_map/x86_{config_map_cpu_model_dict['minCPU']}.xml",
        ]
    )
    tree = ElementTree.fromstring(stdout)

    return [
        feature.get("name") for feature in tree.findall("model")[0].findall("feature")
    ]


@pytest.fixture()
def cpu_test_vm(namespace):
    name = "cpu-test"
    with VirtualMachineForTests(
        name=name, namespace=namespace.name, body=fedora_vm_body(name)
    ) as vm:
        vm.start()
        vm.vmi.wait_until_running()
        yield vm


def node_label_checker(node_label_dict, label_list, dict_key):
    """
    Check node labels for cpu models/features/kvm-info.
    Return dict:
    {'<node_name>': [<cpu_models/features/kvm-info>]}
    """
    return {
        node: [
            value for value in label_list if value in node_label_dict[node][dict_key]
        ]
        for node in node_label_dict
    }


@pytest.mark.polarion("CNV-2797")
def test_obsolete_cpus_in_node_labels(nodes_labels_dict, obsolete_cpus_list):
    """
    Test obsolete CPUs. Obsolete CPUs don't appear in node labels.
    """
    test_dict = node_label_checker(
        node_label_dict=nodes_labels_dict,
        label_list=obsolete_cpus_list,
        dict_key="cpu_models",
    )
    assert not any(test_dict.values()), f"Obsolete CPU found in labels\n{test_dict}"


@pytest.mark.polarion("CNV-2798")
def test_min_cpus_in_node_labels(nodes_labels_dict, libvirt_min_cpu_features_list):
    """
    Test min CPU. Min CPU features don't appear in node labels.
    """
    test_dict = node_label_checker(
        node_label_dict=nodes_labels_dict,
        label_list=libvirt_min_cpu_features_list,
        dict_key="cpu_features",
    )
    assert not any(test_dict.values()), f"Min CPU feature found in labels\n{test_dict}"


@pytest.mark.polarion("CNV-3607")
def test_kvm_info_nfd(nodes_labels_dict):
    kvm_info_nfd_labels = [
        "vpindex",
        "runtime",
        "time",
        "synic",
        "synic2",
        "tlbflush",
        "reset",
        "frequencies",
        "reenlightenment",
        "base",
        "ipi",
        "synictimer",
    ]
    test_dict = node_label_checker(
        node_label_dict=nodes_labels_dict,
        label_list=kvm_info_nfd_labels,
        dict_key="kvm-info",
    )
    assert any(test_dict.values()), f"KVM info not found in labels\n{test_dict}"
