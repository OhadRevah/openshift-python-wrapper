# -*- coding: utf-8 -*-

"""
Tests to check, HCO Namespace Pod's, Security Context Constraint
"""

import logging

import pytest
from pytest_testconfig import config as py_config
from resources.pod import Pod


LOGGER = logging.getLogger(__name__)

POD_SCC_WHITELIST = [
    "restricted",
    "hostpath-provisioner",
    "containerized-data-importer",
    "bridge-marker",
    "linux-bridge",
    "nmstate",
    "ovs-cni-marker",
    "kubevirt-handler",
]


@pytest.fixture(scope="module")
def cnv_pods(default_client):
    yield list(Pod.get(dyn_client=default_client, namespace=py_config["hco_namespace"]))


@pytest.mark.polarion("CNV-4438")
def test_openshiftio_scc_exists_bz1847594(skip_not_openshift, cnv_pods):
    """
    Validate that Pods in hco_namespace (openshift-cnv) have openshift.io/scc
    """
    for pod in cnv_pods:
        assert "openshift.io/scc" in pod.instance.metadata.annotations


@pytest.mark.polarion("CNV-4211")
def test_pods_scc_in_whitelist(skip_not_openshift, cnv_pods):
    """
    Validate that Pods in hco_namespace (openshift-cnv) have SCC from a predefined whitelist.
    """
    bugzilla = {"BZ1834839": "cluster-network-addons-operator"}
    failed_pods = []
    for pod in cnv_pods:
        LOGGER.info(f"Currently Validating {pod.name} Pod.")
        for bug_id, pod_name in bugzilla.items():
            if pod_name in pod.name:
                LOGGER.info(f"Currently a bug {bug_id} for {pod.name}")
                break
        if (
            pod.instance.metadata.annotations["openshift.io/scc"]
            not in POD_SCC_WHITELIST
        ):
            failed_pods.append(pod.name)
    assert not failed_pods, f"Failed pods: {' '.join(failed_pods)}"
